import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from shortlist_ml.config import Settings
from shortlist_ml.db.models import Company, IngestionRun
from shortlist_ml.ingest import rawstore
from shortlist_ml.ingest.companies import CompanyConfig
from shortlist_ml.ingest.http import Fetcher
from shortlist_ml.ingest.sources import SOURCES, ParseError
from shortlist_ml.ingest.store import apply_snapshot

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class _Outcome:
    status: str = "failed"
    http_status: int | None = None
    fetched: int = 0
    new: int = 0
    updated: int = 0
    closed: int = 0
    failed: int = 0
    skipped_by_guard: int = 0
    raw_path: str | None = None
    raw_sha256: str | None = None
    error: str | None = None


def get_or_create_company(session: Session, cfg: CompanyConfig) -> Company:
    company = session.scalars(
        select(Company).where(Company.ats == cfg.ats, Company.board_token == cfg.board_token)
    ).first()
    if company is None:
        company = Company(name=cfg.name, ats=cfg.ats, board_token=cfg.board_token, active=True)
        session.add(company)
    else:
        company.name, company.active = cfg.name, True
    session.flush()
    return company


def _already_ingested(session: Session, company_id: int, raw_path: Path) -> bool:
    return (
        session.scalars(
            select(IngestionRun.id).where(
                IngestionRun.company_id == company_id,
                IngestionRun.raw_path == str(raw_path),
                IngestionRun.status.in_(("ok", "guarded")),
            )
        ).first()
        is not None
    )


def _process(
    session: Session, company: Company, cfg: CompanyConfig, fetcher: Fetcher,
    settings: Settings, now: datetime, force: bool,
) -> _Outcome:  # fmt: skip
    source = SOURCES[cfg.ats]
    out = _Outcome()
    today = now.astimezone(ZoneInfo(settings.timezone)).date()
    existing = rawstore.latest_for_date(settings.raw_dir, cfg.ats, cfg.board_token, today)

    if existing and not force:
        out.raw_path = str(existing)
        if _already_ingested(session, company.id, existing):
            out.status = (
                "skipped"  # today's raw file was already ingested; no network, no DB change
            )
            return out
        content = rawstore.read(existing)  # crashed earlier: replay the saved bytes, don't refetch
    else:
        result = fetcher.get(source.url(cfg.board_token))
        out.http_status = result.status_code or None
        if result.status_code != 200:
            out.failed = 1
            out.error = result.error or f"HTTP {result.status_code}"
            return out
        content = result.content
        source.parse(
            content
        )  # validate BEFORE saving so a garbage response never becomes "today's file"
        path, out.raw_sha256 = rawstore.save(
            settings.raw_dir, cfg.ats, cfg.board_token, content, now, settings.timezone
        )
        out.raw_path = str(path)

    parsed = source.parse(content)
    stats = apply_snapshot(session, company, parsed.postings, now)
    out.fetched, out.new, out.updated, out.closed = (
        stats.fetched,
        stats.new,
        stats.updated,
        stats.closed,
    )
    out.skipped_by_guard, out.failed = stats.skipped_by_guard, parsed.failed
    out.status = "guarded" if stats.guard_reason else "ok"
    if stats.guard_reason:
        out.error = f"close-guard: {stats.guard_reason}"
    return out


def ingest_company(
    session: Session, cfg: CompanyConfig, fetcher: Fetcher, settings: Settings,
    *, clock: Clock = utc_now, force: bool = False, run_group: str | None = None,
) -> IngestionRun:  # fmt: skip
    """Fetch (or replay) one board, update postings, and record an ingestion_runs row.

    A failure for this company (HTTP error, bad payload, DB error) rolls back its postings changes,
    is recorded as status='failed', and never closes anything.
    """
    started = clock()
    company = get_or_create_company(session, cfg)
    session.commit()
    try:
        out = _process(session, company, cfg, fetcher, settings, started, force)
        session.commit()
    except (ParseError, Exception) as exc:
        session.rollback()
        out = _Outcome(failed=1, error=f"{type(exc).__name__}: {str(exc)[:300]}")
    run = IngestionRun(
        run_group=run_group or str(uuid.uuid4()),
        company_id=company.id,
        started_at=started,
        finished_at=clock(),
        status=out.status,
        http_status=out.http_status,
        fetched=out.fetched,
        new=out.new,
        updated=out.updated,
        closed=out.closed,
        failed=out.failed,
        skipped_by_guard=out.skipped_by_guard,
        raw_path=out.raw_path,
        raw_sha256=out.raw_sha256,
        error=out.error,
    )
    session.add(run)
    session.commit()
    return run


def run_all(
    session_factory: sessionmaker[Session], companies: Sequence[CompanyConfig], fetcher: Fetcher,
    settings: Settings, *, clock: Clock = utc_now, force: bool = False,
) -> list[IngestionRun]:  # fmt: skip
    group = str(uuid.uuid4())
    runs: list[IngestionRun] = []
    for cfg in companies:
        with session_factory() as session:
            runs.append(
                ingest_company(
                    session, cfg, fetcher, settings, clock=clock, force=force, run_group=group
                )
            )
    today = clock().astimezone(ZoneInfo(settings.timezone)).date()
    rawstore.prune(settings.raw_dir, settings.raw_retention_days, today)
    return runs
