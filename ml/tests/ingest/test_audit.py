import csv
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from shortlist_ml.db.models import Company
from shortlist_ml.ingest import audit
from shortlist_ml.ingest.normalize import build_posting
from shortlist_ml.ingest.store import apply_snapshot


@pytest.fixture
def populated(session: Session, t0: datetime) -> Session:
    c = Company(name="Acme", ats="greenhouse", board_token="acme", active=True)
    session.add(c)
    session.flush()
    posts = []
    for i in range(30):
        posts.append(
            (f"New Grad Engineer {i}", "Join our program. 0-1 years of experience.", "Austin, TX")
        )
        posts.append(
            (
                f"Senior Engineer {i}",
                "8+ years of experience.",
                "Remote",
            )
        )
    apply_snapshot(
        session,
        c,
        [
            build_posting(
                source="greenhouse",
                external_id=str(i),
                url="https://x.test",
                apply_url=f"https://x.test/{i}",
                title=t,
                description_text=d,
                location_raw=loc,
            )
            for i, (t, d, loc) in enumerate(posts)
        ],
        t0,
    )
    return session


def test_sample_is_seeded_balanced_shuffled_and_blind(populated: Session, tmp_path: Path) -> None:
    rows = audit.make_sample(populated, seed=7, n_each=25)
    again = audit.make_sample(populated, seed=7, n_each=25)
    assert [r["posting_id"] for r in rows] == [r["posting_id"] for r in again]  # deterministic
    assert [r["posting_id"] for r in rows] != [
        r["posting_id"] for r in audit.make_sample(populated, seed=8)
    ]
    assert sum(r["group"] == "flagged" for r in rows) == 25 and len(rows) == 50
    assert [r["group"] for r in rows] != sorted(
        r["group"] for r in rows
    )  # shuffled: position hides the group

    blind, key = tmp_path / "blind.csv", tmp_path / "key.csv"
    audit.write_files(rows, blind, key)
    header = next(csv.reader(blind.open()))
    for hidden in (
        "is_entry_level",
        "entry_evidence",
        "entry_evidence_text",
        "seniority",
        "years_min",
        "sponsorship",
        "group",
        "posting_id",
    ):
        assert hidden not in header
    parsed = list(csv.DictReader(blind.open()))
    assert all(r[c] == "" for r in parsed for c in audit.LABEL_COLUMNS)  # label columns start empty
    assert "is_entry_level" in next(csv.reader(key.open()))


def test_compare_scores_perfect_and_imperfect_labels(populated: Session, tmp_path: Path) -> None:
    rows = audit.make_sample(populated, seed=7, n_each=25)
    blind, key = tmp_path / "blind.csv", tmp_path / "key.csv"
    audit.write_files(rows, blind, key)
    labels = tmp_path / "labels.csv"
    with labels.open("w", newline="") as f:
        w = csv.DictWriter(f, audit.BLIND_COLUMNS)
        w.writeheader()
        for r in rows:  # a labeler who agrees with the rules on entry level and location
            w.writerow({**dict.fromkeys(audit.BLIND_COLUMNS, ""), "n": r["n"],
                        "entry_label": "entry" if r["group"] == "flagged" else "not",
                        "city": r["city"], "region": r["region"], "country": r["country"]})  # fmt: skip
    out = audit.compare(key, labels)
    assert "strict  (labeled 'entry'):          25/25 = 100%" in out
    assert "labeled 'entry': 0/25" in out
    assert "city     exact match 50/50" in out and "country  exact match 50/50" in out
    assert "1.00" not in out  # no second labeler given

    other = tmp_path / "other.csv"
    with other.open("w", newline="") as f:  # a second labeler who calls everything 'maybe'
        w = csv.DictWriter(f, audit.BLIND_COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow(
                {**dict.fromkeys(audit.BLIND_COLUMNS, ""), "n": r["n"], "entry_label": "maybe"}
            )
    assert "Cohen's kappa = 0.00" in audit.compare(key, labels, other)


def test_wilson_and_kappa_basics() -> None:
    lo, hi = audit.wilson(9, 25)
    assert 0.19 < lo < 0.21 and 0.54 < hi < 0.56  # matches the 36% [20-55] quoted in the audit doc
    assert audit.cohen_kappa(["a", "b"], ["a", "b"]) == 1.0
