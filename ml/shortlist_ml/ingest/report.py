"""Markdown report of what is in the database: per-company counts and ingestion-run statistics."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import ColumnElement, case, func, select
from sqlalchemy.orm import Session

from shortlist_ml.db.models import Company, IngestionRun, Posting


def _n(expr: Any) -> ColumnElement[Any]:
    return func.coalesce(func.sum(case((expr, 1), else_=0)), 0)


def build_report(session: Session, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    open_ = Posting.closed_at.is_(None)
    cols: list[Any] = [
        Company.name,
        Company.ats,
        func.count(Posting.id),
        _n(Posting.is_entry_level),
        _n(Posting.seniority == "intern"),
        _n(Posting.country == "US"),
        _n(Posting.country.is_(None)),
        _n(Posting.is_remote.is_(True)),
        _n(Posting.canonical_id.is_not(None)),
    ]
    rows = session.execute(
        select(*cols)
        .join(Posting, Posting.company_id == Company.id)
        .where(open_)
        .group_by(Company.id)
        .order_by(func.count(Posting.id).desc(), Company.name)
    ).all()
    total = [sum(int(r[i]) for r in rows) for i in range(2, 9)]

    lines = [
        "# Ingest report",
        "",
        f"Generated {now:%Y-%m-%d %H:%M} UTC by `make report`. Counts are OPEN postings (not closed).",
        "`entry-level` is a soft, noisy signal (see `heuristic-audit.md`); `country unknown` postings are never excluded.",
        "",
        "| Company | ATS | Postings | Entry-level | Intern | US | Country unknown | Remote | Repost-group members |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, ats, *counts in rows:
        lines.append(f"| {name} | {ats} | " + " | ".join(str(int(c)) for c in counts) + " |")
    lines.append("| **Total** | | " + " | ".join(f"**{t}**" for t in total) + " |")

    # Evidence mix for the entry-level flag and the sponsorship values.
    ev = session.execute(
        select(Posting.entry_evidence, func.count())
        .where(open_, Posting.is_entry_level.is_(True))
        .group_by(Posting.entry_evidence)
    ).all()
    sp = session.execute(
        select(Posting.sponsorship, func.count()).where(open_).group_by(Posting.sponsorship)
    ).all()
    closed = session.scalar(select(func.count()).where(Posting.closed_at.is_not(None))) or 0
    lines += [
        "",
        "## Signals",
        "",
        "Entry-level by evidence: "
        + (
            ", ".join(f"{k or 'none'} {v}" for k, v in sorted(ev, key=lambda x: str(x[0])))
            or "none"
        ),
        "",
        "Sponsorship: " + ", ".join(f"{k} {v}" for k, v in sorted(sp)),
        "",
        f"Closed postings (not counted above): {closed}",
        "",
        "## Ingestion runs",
        "",
        "Latest run per company, then totals over all runs.",
        "",
        "| Company | Status | Started (UTC) | Fetched | New | Updated | Reopened | Closed | Failed | Skipped by guard |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    latest = (
        select(IngestionRun.company_id, func.max(IngestionRun.id).label("rid"))
        .group_by(IngestionRun.company_id)
        .subquery()
    )
    runs = session.execute(
        select(Company.name, IngestionRun)
        .join(IngestionRun, IngestionRun.company_id == Company.id)
        .join(latest, latest.c.rid == IngestionRun.id)
        .order_by(Company.name)
    ).all()
    for name, r in runs:
        lines.append(
            f"| {name} | {r.status} | {r.started_at:%Y-%m-%d %H:%M} | {r.fetched} | {r.new} | {r.updated} | {r.reopened} | "
            f"{r.closed} | {r.failed} | {r.skipped_by_guard} |"
        )
    agg = session.execute(
        select(
            IngestionRun.status,
            func.count(),
            func.sum(IngestionRun.fetched),
            func.sum(IngestionRun.new),
            func.sum(IngestionRun.updated),
            func.sum(IngestionRun.reopened),
            func.sum(IngestionRun.closed),
            func.sum(IngestionRun.failed),
            func.sum(IngestionRun.skipped_by_guard),
        )
        .group_by(IngestionRun.status)
        .order_by(IngestionRun.status)
    ).all()
    lines += [
        "",
        "Totals over all runs, by status:",
        "",
        "| Status | Runs | Fetched | New | Updated | Reopened | Closed | Failed | Skipped by guard |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for status, *vals in agg:
        lines.append(f"| {status} | " + " | ".join(str(int(v or 0)) for v in vals) + " |")
    return "\n".join(lines) + "\n"
