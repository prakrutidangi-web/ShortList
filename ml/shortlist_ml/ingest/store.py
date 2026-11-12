"""Apply one company's board snapshot to the database.

Timestamp semantics (they feed time-based train/eval splits, so they are tested):
  first_seen_at  set once, when we first observe the posting; never changes
  last_seen_at   set to the run time on every snapshot that contains the posting
  closed_at      set when a *trusted* snapshot no longer contains it; cleared if it reappears
  updated_at     set when the content hash changes (an edit); NULL if never edited
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from shortlist_ml.db.models import Company, Posting
from shortlist_ml.ingest.dedup import dedup_key
from shortlist_ml.ingest.normalize import NormalizedPosting, derive_fields

# Close nothing if the snapshot has fewer than this fraction of the postings we thought were open.
DROP_GUARD_FRACTION = 0.5


@dataclass
class StoreResult:
    fetched: int = 0
    new: int = 0
    updated: int = 0
    closed: int = 0
    skipped_by_guard: int = 0
    guard_reason: str | None = None


_CONTENT_FIELDS = (
    "url", "apply_url", "title", "description_text", "location_raw", "city", "region", "country",
    "is_remote", "years_min", "seniority", "is_entry_level", "entry_evidence", "entry_evidence_text",
    "sponsorship", "sponsorship_evidence", "source_posted_at",
    "source_updated_at", "content_hash",
)  # fmt: skip


def _copy_fields(row: Posting, p: NormalizedPosting) -> None:
    for name in _CONTENT_FIELDS:
        setattr(row, name, getattr(p, name))


def apply_snapshot(
    session: Session, company: Company, postings: Sequence[NormalizedPosting], now: datetime
) -> StoreResult:
    """Upsert `postings`, detect edits and reposts, and close postings that disappeared.

    Re-running with the same snapshot is idempotent apart from last_seen_at advancing.
    """
    result = StoreResult()
    incoming: dict[str, NormalizedPosting] = {}
    for p in postings:
        incoming[p.external_id] = p  # a duplicated id within one payload: last one wins
    result.fetched = len(incoming)

    existing = {
        (row.source, row.external_id): row
        for row in session.scalars(select(Posting).where(Posting.company_id == company.id))
    }
    open_before = [row for row in existing.values() if row.closed_at is None]

    for p in incoming.values():
        row = existing.get((p.source, p.external_id))
        if row is None:
            _insert(session, company, p, now)
            result.new += 1
            continue
        row.last_seen_at = now
        changed = False
        if row.closed_at is not None:  # reappeared
            row.closed_at = None
            changed = True
        if row.content_hash != p.content_hash:  # edited in place: NOT a repost
            _copy_fields(row, p)
            row.dedup_key = dedup_key(company.id, p)
            row.updated_at = now
            changed = True
        if changed:
            result.updated += 1

    seen = {(p.source, p.external_id) for p in incoming.values()}
    missing = [row for row in open_before if (row.source, row.external_id) not in seen]
    if missing:
        reason = None
        if result.fetched == 0:
            reason = "empty snapshot"
        elif result.fetched < DROP_GUARD_FRACTION * len(open_before):
            reason = (
                f"snapshot has {result.fetched} postings vs {len(open_before)} open (>50% drop)"
            )
        if reason:
            result.skipped_by_guard = len(missing)
            result.guard_reason = reason
        else:
            for row in missing:
                row.closed_at = now
            result.closed = len(missing)
    session.flush()
    return result


def _insert(session: Session, company: Company, p: NormalizedPosting, now: datetime) -> None:
    key = dedup_key(company.id, p)
    # Repost detection: same content under a different ATS id. Join the existing group.
    root = session.scalars(
        select(Posting)
        .where(Posting.company_id == company.id, Posting.dedup_key == key)
        .order_by(Posting.first_seen_at, Posting.id)
        .limit(1)
    ).first()
    row = Posting(
        company_id=company.id,
        source=p.source,
        external_id=p.external_id,
        first_seen_at=now,
        last_seen_at=now,
        dedup_key=key,
        canonical_id=(root.canonical_id or root.id) if root else None,
        **{name: getattr(p, name) for name in _CONTENT_FIELDS},
    )
    session.add(row)
    session.flush()  # so later postings in the same snapshot can find this one as a group root


def current_postings(session: Session, company_id: int | None = None) -> list[Posting]:
    """Open postings, one per repost group (the most recently first-seen open member)."""
    stmt = select(Posting).where(Posting.closed_at.is_(None))
    if company_id is not None:
        stmt = stmt.where(Posting.company_id == company_id)
    best: dict[int, Posting] = {}
    for row in session.scalars(stmt.order_by(Posting.first_seen_at, Posting.id)):
        best[row.canonical_id or row.id] = row  # later rows overwrite earlier ones
    return list(best.values())


def reparse_all(session: Session) -> int:
    """Re-derive rule-based fields (location, years, seniority, sponsorship) from stored text.

    For use after normalization rules change: ingest does not refresh these when the posting text is
    unchanged. Touches NO timestamps (a rule change is not a posting edit). For Lever rows the
    `remote_hint`/`country_hint` are not stored, so is_remote and country only ever gain information.
    Returns the number of rows whose derived fields changed.
    """
    changed = 0
    for row in session.scalars(select(Posting)):
        d = derive_fields(row.title, row.description_text, row.location_raw)
        # Lever rows may carry hint-derived country/is_remote (workplaceType, country) that are not
        # recoverable from the text, so for them reparse only adds information. Others recompute fully.
        keep_hints = row.source == "lever"
        new = {
            "city": d.city, "region": d.region, "country": (d.country or row.country) if keep_hints else d.country,
            "is_remote": True if (keep_hints and (d.is_remote or row.is_remote)) else d.is_remote,
            "years_min": d.years_min, "seniority": d.seniority,
            "is_entry_level": d.is_entry_level, "entry_evidence": d.entry_evidence,
            "entry_evidence_text": d.entry_evidence_text, "sponsorship": d.sponsorship,
            "sponsorship_evidence": d.sponsorship_evidence,
        }  # fmt: skip
        diff = {k: v for k, v in new.items() if getattr(row, k) != v}
        for k, v in diff.items():
            setattr(row, k, v)
        changed += bool(diff)
    session.flush()
    return changed
