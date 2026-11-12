"""Blind audit samples for the rule-based fields.

`make_sample` draws a seeded random sample (half flagged, half not, then shuffled so position reveals
nothing) and writes TWO files: a blind CSV for a human labeler (company, title, location text, link,
excerpt, empty label columns; NO rule output) and a key CSV (what the rules said) that stays local.
`compare` scores the rules against a filled-in label file.
"""

import csv
import math
import random
import re
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from shortlist_ml.db.models import Company, Posting

LABEL_COLUMNS = ["entry_label", "city", "region", "country", "sponsorship_label", "notes"]
BLIND_COLUMNS = ["n", "company", "title", "location_raw", "apply_url", "excerpt", *LABEL_COLUMNS]
KEY_COLUMNS = [
    "n", "posting_id", "group", "is_entry_level", "entry_evidence", "entry_evidence_text",
    "seniority", "years_min", "city", "region", "country", "sponsorship", "sponsorship_evidence",
]  # fmt: skip
ENTRY_LABELS = (
    "entry",
    "maybe",
    "not",
)  # entry: 0-1 yr / new grad can apply; maybe: ~1-3 yrs or ambiguous

_SNIP = re.compile(
    r"(\d{1,2}\s*\+?\s*(?:-|to)?\s*\d{0,2}\s*\+?\s*years?[^.\n]{0,70}|new[- ]?grad\w*|early[- ]career|"
    r"entry[- ]level|recent graduate\w*|class of 20\d\d)",
    re.I,
)


def excerpt(description: str, limit: int = 700) -> str:
    """Opening text plus a few snippets around experience / early-career wording, for a quick read."""
    flat = re.sub(r"\s+", " ", description).strip()
    head = flat[:260]
    snippets: list[str] = []
    for m in _SNIP.finditer(flat):
        a = max(0, m.start() - 60)
        snippets.append(flat[a : m.end() + 40])
        if len(snippets) == 4:
            break
    return (head + " … " + " | ".join(snippets))[:limit]


def make_sample(session: Session, seed: int, n_each: int = 25) -> list[dict[str, str]]:
    """Return merged blind+key rows (keys are split into separate files by the caller)."""
    rows = list(
        session.execute(
            select(Posting, Company.name)
            .join(Company, Company.id == Posting.company_id)
            .where(Posting.closed_at.is_(None))
            .order_by(Posting.id)
        )
    )
    rng = random.Random(seed)
    flagged = [r for r in rows if r[0].is_entry_level]
    plain = [r for r in rows if not r[0].is_entry_level]
    picked = [(r, "flagged") for r in rng.sample(flagged, n_each)] + [
        (r, "unflagged") for r in rng.sample(plain, n_each)
    ]
    rng.shuffle(picked)
    out = []
    for i, ((p, company), group) in enumerate(picked, 1):
        out.append(
            {
                "n": str(i), "posting_id": str(p.id), "group": group, "company": company,
                "title": p.title, "location_raw": p.location_raw or "", "apply_url": p.apply_url,
                "excerpt": excerpt(p.description_text), "is_entry_level": str(p.is_entry_level),
                "entry_evidence": p.entry_evidence or "", "entry_evidence_text": p.entry_evidence_text or "",
                "seniority": p.seniority, "years_min": "" if p.years_min is None else str(p.years_min),
                "city": p.city or "", "region": p.region or "", "country": p.country or "",
                "sponsorship": p.sponsorship, "sponsorship_evidence": p.sponsorship_evidence or "",
            }
        )  # fmt: skip
    return out


def write_files(rows: list[dict[str, str]], blind_path: Path, key_path: Path) -> None:
    with blind_path.open("w", newline="") as f:
        w = csv.DictWriter(f, BLIND_COLUMNS)
        w.writeheader()
        for r in rows:
            # Label columns (incl. city/region/country, which share names with the rule output) start EMPTY.
            w.writerow({c: ("" if c in LABEL_COLUMNS else r.get(c, "")) for c in BLIND_COLUMNS})
    with key_path.open("w", newline="") as f:
        w = csv.DictWriter(f, KEY_COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in KEY_COLUMNS})


# ---------------------------------------------------------------- scoring
def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (math.nan, math.nan)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    a = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - a) / d, (c + a) / d


def cohen_kappa(a: list[str], b: list[str]) -> float:
    n = len(a)
    if n == 0:
        return math.nan
    po = sum(x == y for x, y in zip(a, b, strict=True)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def _read(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="") as f:
        return {r["n"]: r for r in csv.DictReader(f)}


def _fmt(k: int, n: int) -> str:
    lo, hi = wilson(k, n)
    return (
        f"{k}/{n} = {100 * k / n:.0f}% [95% CI {100 * lo:.0f}-{100 * hi:.0f}%]"
        if n
        else "n/a (0 rows)"
    )


def compare(key_path: Path, labels_path: Path, other_labels: Path | None = None) -> str:
    key, lab = _read(key_path), _read(labels_path)
    ns = sorted(key, key=int)
    lines = [f"Compared {len(ns)} rows. Labels: {labels_path.name}", ""]
    bad = [
        n for n in ns if lab.get(n, {}).get("entry_label", "").strip().lower() not in ENTRY_LABELS
    ]
    if bad:
        lines.append(
            f"WARNING: {len(bad)} rows have a missing/invalid entry_label (use {ENTRY_LABELS}): n={bad[:10]}"
        )
    flagged = [n for n in ns if key[n]["is_entry_level"] == "True" and n not in bad]
    unflagged = [n for n in ns if key[n]["is_entry_level"] != "True" and n not in bad]

    def lab_of(n: str) -> str:
        return lab[n]["entry_label"].strip().lower()

    strict = sum(lab_of(n) == "entry" for n in flagged)
    lenient = sum(lab_of(n) in ("entry", "maybe") for n in flagged)
    lines += [
        "ENTRY-LEVEL FLAG (precision of the rows the rules flagged)",
        f"  strict  (labeled 'entry'):          {_fmt(strict, len(flagged))}",
        f"  lenient (labeled 'entry'/'maybe'):  {_fmt(lenient, len(flagged))}",
        f"  labeled 'not' (clearly wrong):      {_fmt(sum(lab_of(n) == 'not' for n in flagged), len(flagged))}",
    ]
    for rule in ("title_keyword", "phrase", "years"):
        sub = [n for n in flagged if key[n]["entry_evidence"] == rule]
        lines.append(
            f"  by rule {rule:13}: n={len(sub)}  entry={sum(lab_of(n) == 'entry' for n in sub)}  maybe={sum(lab_of(n) == 'maybe' for n in sub)}  not={sum(lab_of(n) == 'not' for n in sub)}"
        )
    missed = [n for n in unflagged if lab_of(n) == "entry"]
    lines += [
        "",
        "UNFLAGGED rows the labeler thinks are entry-level (misses; not a recall estimate):",
        f"  labeled 'entry': {_fmt(len(missed), len(unflagged))};  'maybe': {sum(lab_of(n) == 'maybe' for n in unflagged)}",
    ]
    if missed:
        lines.append(
            "  rows: "
            + ", ".join(
                f"{n} ({key[n]['seniority']}, years={key[n]['years_min'] or '-'})" for n in missed
            )
        )

    lines += [
        "",
        "LOCATION (rules vs labeler's city/region/country; blank label = 'no such info in the text')",
    ]
    for field in ("city", "region", "country"):
        ok = tot = 0
        wrong: list[str] = []
        for n in ns:
            truth = lab.get(n, {}).get(field, "").strip().lower()
            got = key[n][field].strip().lower()
            tot += 1
            if truth == got:
                ok += 1
            else:
                wrong.append(f"{n}: '{key[n][field]}' vs '{lab[n][field]}'")
        lines.append(
            f"  {field:8} exact match {_fmt(ok, tot)}" + (f"   e.g. {wrong[:3]}" if wrong else "")
        )

    rows_sp = [n for n in ns if lab.get(n, {}).get("sponsorship_label", "").strip()]
    if rows_sp:
        agree = sum(
            lab[n]["sponsorship_label"].strip().lower() == key[n]["sponsorship"] for n in rows_sp
        )
        lines += ["", f"SPONSORSHIP (only rows you labeled): agreement {_fmt(agree, len(rows_sp))}"]
    if other_labels:
        o = _read(other_labels)
        common = [
            n
            for n in ns
            if n in o
            and n not in bad
            and o[n].get("entry_label", "").strip().lower() in ENTRY_LABELS
        ]
        a = [lab_of(n) for n in common]
        b = [o[n]["entry_label"].strip().lower() for n in common]
        agree = sum(x == y for x, y in zip(a, b, strict=True))
        lines += [
            "",
            f"LABELER AGREEMENT on entry_label ({other_labels.name}): {_fmt(agree, len(common))}, Cohen's kappa = {cohen_kappa(a, b):.2f}",
            "  disagreements (n: this vs other): "
            + ", ".join(f"{n}: {x} vs {y}" for n, x, y in zip(common, a, b, strict=True) if x != y),
        ]
    lines += [
        "",
        "Small-sample note: every interval above is wide; do not claim a difference whose intervals overlap.",
    ]
    return "\n".join(lines)


def iter_dicts(path: Path) -> Iterable[dict[str, str]]:
    with path.open(newline="") as f:
        yield from csv.DictReader(f)
