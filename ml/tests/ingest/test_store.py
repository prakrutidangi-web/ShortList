from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shortlist_ml.db.models import Company, Posting
from shortlist_ml.ingest.normalize import NormalizedPosting, build_posting
from shortlist_ml.ingest.store import apply_snapshot, current_postings, reparse_all

DAY = timedelta(days=1)


def post(
    ext: str, title: str = "Software Engineer", desc: str = "Build things.", loc: str = "Austin, TX"
) -> NormalizedPosting:
    return build_posting(
        source="greenhouse", external_id=ext, url=f"https://x.test/{ext}", apply_url=f"https://x.test/{ext}",
        title=title, description_text=desc, location_raw=loc,
    )  # fmt: skip


@pytest.fixture
def company(session: Session) -> Company:
    c = Company(name="Acme", ats="greenhouse", board_token="acme", active=True)
    session.add(c)
    session.flush()
    return c


def rows(session: Session) -> dict[str, Posting]:
    return {p.external_id: p for p in session.scalars(select(Posting))}


def test_timestamps_across_open_close_reopen(
    session: Session, company: Company, t0: datetime
) -> None:
    t1, t2 = t0 + DAY, t0 + 2 * DAY
    r0 = apply_snapshot(session, company, [post("a"), post("b")], t0)
    assert (r0.new, r0.updated, r0.closed) == (2, 0, 0)

    r1 = apply_snapshot(session, company, [post("a")], t1)  # b vanished; 1 >= 50% of 2, so trusted
    assert (r1.new, r1.closed, r1.skipped_by_guard) == (0, 1, 0)
    a, b = rows(session)["a"], rows(session)["b"]
    assert a.first_seen_at == t0 and a.last_seen_at == t1 and a.closed_at is None
    assert b.first_seen_at == t0 and b.last_seen_at == t0 and b.closed_at == t1

    r2 = apply_snapshot(session, company, [post("a"), post("b")], t2)  # b reappears
    b = rows(session)["b"]
    assert r2.updated == 1 and r2.new == 0
    assert b.first_seen_at == t0 and b.last_seen_at == t2 and b.closed_at is None
    assert b.updated_at is None  # reopening is not a content edit


def test_rerun_is_idempotent(session: Session, company: Company, t0: datetime) -> None:
    snap = [post("a"), post("b", title="Data Engineer")]
    apply_snapshot(session, company, snap, t0)
    before = {
        k: (p.first_seen_at, p.content_hash, p.updated_at, p.closed_at, p.canonical_id)
        for k, p in rows(session).items()
    }
    result = apply_snapshot(session, company, snap, t0 + timedelta(hours=1))
    after = {
        k: (p.first_seen_at, p.content_hash, p.updated_at, p.closed_at, p.canonical_id)
        for k, p in rows(session).items()
    }
    assert (result.new, result.updated, result.closed, result.skipped_by_guard) == (0, 0, 0, 0)
    assert before == after
    assert session.scalar(select(func.count()).select_from(Posting)) == 2
    assert all(
        p.last_seen_at == t0 + timedelta(hours=1) for p in rows(session).values()
    )  # the only change


def test_edit_updates_in_place_and_is_not_a_repost(
    session: Session, company: Company, t0: datetime
) -> None:
    apply_snapshot(session, company, [post("a", desc="v1")], t0)
    t1 = t0 + DAY
    result = apply_snapshot(
        session, company, [post("a", desc="v2 with 3+ years of experience")], t1
    )
    assert (result.new, result.updated) == (0, 1)
    a = rows(session)["a"]
    assert session.scalar(select(func.count()).select_from(Posting)) == 1
    assert a.description_text.startswith("v2") and a.updated_at == t1 and a.first_seen_at == t0
    assert a.canonical_id is None and a.years_min == 3


def test_repost_joins_group_and_current_returns_one(
    session: Session, company: Company, t0: datetime
) -> None:
    apply_snapshot(session, company, [post("old"), post("keep", title="Other")], t0)
    t1 = t0 + DAY
    apply_snapshot(
        session, company, [post("keep", title="Other")], t1
    )  # "old" closes (1 of 2 kept)
    t2 = t0 + 2 * DAY
    apply_snapshot(
        session, company, [post("keep", title="Other"), post("new")], t2
    )  # same content, new id
    r = rows(session)
    assert r["old"].canonical_id is None and r["old"].closed_at == t1
    assert r["new"].canonical_id == r["old"].id and r["new"].dedup_key == r["old"].dedup_key
    assert r["keep"].canonical_id is None
    assert {p.external_id for p in current_postings(session)} == {"keep", "new"}


def test_same_content_open_twice_collapses_to_latest(
    session: Session, company: Company, t0: datetime
) -> None:
    apply_snapshot(session, company, [post("x1"), post("x2")], t0)  # identical content, two ids
    r = rows(session)
    assert r["x1"].canonical_id is None and r["x2"].canonical_id == r["x1"].id
    assert [p.external_id for p in current_postings(session)] == ["x2"]


def test_different_location_or_company_is_not_a_repost(
    session: Session, company: Company, t0: datetime
) -> None:
    apply_snapshot(session, company, [post("a", loc="Austin, TX"), post("b", loc="Boston, MA")], t0)
    assert all(p.canonical_id is None for p in rows(session).values())
    other = Company(name="Beta", ats="greenhouse", board_token="beta", active=True)
    session.add(other)
    session.flush()
    apply_snapshot(
        session, other, [post("a", loc="Austin, TX")], t0
    )  # same ext id & content, other company
    assert session.scalar(select(func.count()).select_from(Posting)) == 3
    assert all(p.canonical_id is None for p in session.scalars(select(Posting)))


def test_duplicate_ids_in_one_payload_last_wins(
    session: Session, company: Company, t0: datetime
) -> None:
    result = apply_snapshot(
        session, company, [post("a", desc="first"), post("a", desc="second")], t0
    )
    assert result.fetched == 1 and rows(session)["a"].description_text == "second"


# ---- closed-posting guard
def _open_n(session: Session, company: Company, n: int, t0: datetime) -> list[NormalizedPosting]:
    snap = [post(f"p{i}", title=f"Role {i}") for i in range(n)]
    apply_snapshot(session, company, snap, t0)
    return snap


def test_guard_empty_snapshot_closes_nothing(
    session: Session, company: Company, t0: datetime
) -> None:
    _open_n(session, company, 10, t0)
    result = apply_snapshot(session, company, [], t0 + DAY)
    assert (result.closed, result.skipped_by_guard) == (
        0,
        10,
    ) and result.guard_reason == "empty snapshot"
    assert all(p.closed_at is None for p in rows(session).values())


def test_guard_big_drop_closes_nothing_but_keeps_seen_fresh(
    session: Session, company: Company, t0: datetime
) -> None:
    snap = _open_n(session, company, 10, t0)
    t1 = t0 + DAY
    result = apply_snapshot(session, company, snap[:4], t1)  # 4 < 50% of 10
    assert (result.closed, result.skipped_by_guard) == (0, 6) and result.guard_reason
    r = rows(session)
    assert all(p.closed_at is None for p in r.values())
    assert r["p0"].last_seen_at == t1 and r["p9"].last_seen_at == t0  # still-seen rows are updated


def test_guard_boundary_exactly_half_is_trusted(
    session: Session, company: Company, t0: datetime
) -> None:
    snap = _open_n(session, company, 10, t0)
    result = apply_snapshot(session, company, snap[:5], t0 + DAY)  # 5 == 50%: not a >50% drop
    assert (result.closed, result.skipped_by_guard, result.guard_reason) == (5, 0, None)
    assert sum(p.closed_at is not None for p in rows(session).values()) == 5


def test_first_ever_snapshot_empty_is_fine(
    session: Session, company: Company, t0: datetime
) -> None:
    result = apply_snapshot(session, company, [], t0)
    assert (result.fetched, result.closed, result.skipped_by_guard, result.guard_reason) == (
        0,
        0,
        0,
        None,
    )


def test_naive_datetimes_are_rejected(session: Session, company: Company) -> None:
    with pytest.raises(Exception, match="naive"):
        apply_snapshot(session, company, [post("a")], datetime(2026, 1, 1))


def test_stored_times_roundtrip_as_utc(session: Session, company: Company, t0: datetime) -> None:
    apply_snapshot(session, company, [post("a")], t0)
    session.expire_all()
    assert rows(session)["a"].first_seen_at == t0 and rows(session)["a"].first_seen_at.tzinfo == UTC


def test_reparse_rederives_fields_without_touching_timestamps(
    session: Session, company: Company, t0: datetime
) -> None:
    apply_snapshot(
        session,
        company,
        [
            post(
                "a",
                title="Software Engineer, New Grad",
                desc="0-2 years of experience",
                loc="Austin, Texas",
            )
        ],
        t0,
    )
    row = rows(session)["a"]
    stamps = (row.first_seen_at, row.last_seen_at, row.updated_at, row.closed_at, row.content_hash)
    # Simulate rows written by an older, worse parser.
    row.country, row.region, row.seniority, row.is_entry_level, row.sponsorship = (
        "Texas",
        None,
        "unknown",
        False,
        "restricted",
    )
    session.flush()
    assert reparse_all(session) == 1
    row = rows(session)["a"]
    assert (row.country, row.region, row.seniority, row.is_entry_level, row.sponsorship) == (
        "US",
        "TX",
        "entry",
        True,
        "unknown",
    )
    assert stamps == (
        row.first_seen_at,
        row.last_seen_at,
        row.updated_at,
        row.closed_at,
        row.content_hash,
    )
    assert reparse_all(session) == 0  # idempotent
