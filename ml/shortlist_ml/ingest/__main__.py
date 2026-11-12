import argparse
import sys
import time
from datetime import UTC, datetime
from datetime import time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

from shortlist_ml.config import get_settings
from shortlist_ml.db.session import make_engine, make_session_factory
from shortlist_ml.ingest import rawstore
from shortlist_ml.ingest.companies import load_companies
from shortlist_ml.ingest.http import Fetcher, RateLimiter, make_client
from shortlist_ml.ingest.run import run_all
from shortlist_ml.ingest.schedule import next_run_at
from shortlist_ml.ingest.store import reparse_all
from shortlist_ml.ingest.verify_companies import verify_all


def _fetcher() -> Fetcher:
    s = get_settings()
    return Fetcher(make_client(s.user_agent), RateLimiter(s.request_interval_s))


def cmd_run(args: argparse.Namespace) -> int:
    s = get_settings()
    companies = load_companies(s.companies_file)
    if args.company:
        companies = [
            c
            for c in companies
            if c.name.lower() == args.company.lower() or c.board_token == args.company
        ]
        if not companies:
            print(f"no company matching {args.company!r} in {s.companies_file}", file=sys.stderr)
            return 2
    factory = make_session_factory(make_engine(s.database_url))
    runs = run_all(factory, companies, _fetcher(), s, force=args.force)
    print(
        f"{'company':28} {'status':8} {'fetched':>7} {'new':>5} {'upd':>5} {'closed':>6} {'fail':>5} {'guard':>5}"
    )
    names = {c.board_token: c.name for c in companies}
    for cfg, r in zip(companies, runs, strict=True):
        print(
            f"{names[cfg.board_token][:28]:28} {r.status:8} {r.fetched:7} {r.new:5} {r.updated:5} "
            f"{r.closed:6} {r.failed:5} {r.skipped_by_guard:5}"
            + (f"  [{r.error}]" if r.error else "")
        )
    return 1 if any(r.status == "failed" for r in runs) else 0


def cmd_verify(args: argparse.Namespace) -> int:
    s = get_settings()
    results = verify_all(s.candidates_file, s.companies_file, args.report, _fetcher())
    for r in results:
        print(
            f"{'OK  ' if r.ok else 'FAIL'} {r.company.ats:10} {r.company.board_token:28} {r.jobs:5}  {'' if r.ok else r.detail}"
        )
    print(
        f"\n{sum(r.ok for r in results)}/{len(results)} verified; wrote {s.companies_file} and {args.report}"
    )
    return 0


def cmd_reparse(args: argparse.Namespace) -> int:
    s = get_settings()
    with make_session_factory(make_engine(s.database_url))() as session:
        changed = reparse_all(session)
        session.commit()
    print(f"re-derived rule-based fields; {changed} posting(s) changed (timestamps untouched)")
    return 0


def cmd_clean_raw(args: argparse.Namespace) -> int:
    s = get_settings()
    today = datetime.now(UTC).astimezone(ZoneInfo(s.timezone)).date()
    removed = rawstore.prune(
        s.raw_dir, args.keep_days or s.raw_retention_days, today, dry_run=args.dry_run
    )
    verb = "would delete" if args.dry_run else "deleted"
    print(
        f"{verb} {len(removed)} raw file(s) older than {args.keep_days or s.raw_retention_days} days"
    )
    return 0


def cmd_schedule(args: argparse.Namespace) -> int:
    s = get_settings()
    hh, mm = (int(x) for x in args.at.split(":"))
    while True:
        target = next_run_at(datetime.now(UTC), dtime(hh, mm), s.timezone)
        print(f"next ingest at {target.isoformat()}", flush=True)
        while (remaining := (target - datetime.now(UTC)).total_seconds()) > 0:
            time.sleep(min(remaining, 300))
        cmd_run(argparse.Namespace(company=None, force=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m shortlist_ml.ingest")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("run", help="fetch boards in companies.yaml and update the database")
    p_run.add_argument(
        "--force", action="store_true", help="refetch even if today's raw file exists"
    )
    p_run.add_argument("--company", help="only this company (name or board token)")
    p_run.set_defaults(fn=cmd_run)
    p_ver = sub.add_parser(
        "verify-companies", help="verify companies.candidates.yaml against live APIs"
    )
    p_ver.add_argument(
        "--report",
        type=Path,
        default=Path("docs/company-verification.md"),
    )
    p_ver.set_defaults(fn=cmd_verify)
    p_rp = sub.add_parser(
        "reparse", help="re-derive rule-based fields for stored postings after a rule change"
    )
    p_rp.set_defaults(fn=cmd_reparse)
    p_cl = sub.add_parser("clean-raw", help="delete raw files past the retention window")
    p_cl.add_argument("--keep-days", type=int)
    p_cl.add_argument("--dry-run", action="store_true")
    p_cl.set_defaults(fn=cmd_clean_raw)
    p_sc = sub.add_parser(
        "schedule", help="run `run` daily at HH:MM local time (optional alternative to cron)"
    )
    p_sc.add_argument("--at", default="06:00")
    p_sc.set_defaults(fn=cmd_schedule)
    args = parser.parse_args(argv)
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
