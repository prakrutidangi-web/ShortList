import json
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from shortlist_ml.config import Settings
from shortlist_ml.db.models import IngestionRun, Posting
from shortlist_ml.db.session import make_engine
from shortlist_ml.ingest import __main__ as cli
from shortlist_ml.ingest.companies import CompanyConfig
from shortlist_ml.ingest.http import Fetcher
from shortlist_ml.ingest.run import run_all

DAY = timedelta(days=1)
ACME = CompanyConfig("Acme", "greenhouse", "acme")
BETA = CompanyConfig("Beta", "lever", "beta")
FetcherFor = Callable[[Callable[[httpx.Request], httpx.Response]], Fetcher]


class Net:
    """Scriptable fake of the two ATS hosts; counts requests per host."""

    def __init__(self, fixtures: Path) -> None:
        self.gh = (fixtures / "greenhouse.json").read_bytes()
        self.lever = (fixtures / "lever.json").read_bytes()
        self.gh_status = self.lever_status = 200
        self.calls: list[str] = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.calls.append(req.url.host)
        if req.url.host == "boards-api.greenhouse.io":
            return httpx.Response(self.gh_status, content=self.gh)
        return httpx.Response(self.lever_status, content=self.lever)


@pytest.fixture
def net(fixtures_dir: Path) -> Net:
    return Net(fixtures_dir)


@pytest.fixture
def factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


def count(factory: sessionmaker[Session], model: type) -> int:
    with factory() as s:
        return int(s.scalar(select(func.count()).select_from(model)) or 0)


def test_run_ingests_both_sources_and_records_stats(
    factory: sessionmaker[Session],
    net: Net,
    fetcher_for: FetcherFor,
    settings: Settings,
    t0: datetime,
) -> None:
    runs = run_all(factory, [ACME, BETA], fetcher_for(net), settings, clock=lambda: t0)
    assert [r.status for r in runs] == ["ok", "ok"]
    assert [
        (r.fetched, r.new, r.updated, r.closed, r.failed, r.skipped_by_guard) for r in runs
    ] == [(3, 3, 0, 0, 0, 0), (2, 2, 0, 0, 0, 0)]
    assert (
        runs[0].http_status == 200 and runs[0].raw_sha256 and Path(runs[0].raw_path or "").exists()
    )
    assert len({r.run_group for r in runs}) == 1
    assert count(factory, Posting) == 5


def test_rerun_same_day_is_skipped_and_force_changes_nothing(
    factory: sessionmaker[Session],
    net: Net,
    fetcher_for: FetcherFor,
    settings: Settings,
    t0: datetime,
) -> None:
    run_all(factory, [ACME], fetcher_for(net), settings, clock=lambda: t0)
    with factory() as s:
        snapshot = {
            p.external_id: (p.first_seen_at, p.last_seen_at, p.content_hash, p.closed_at)
            for p in s.scalars(select(Posting))
        }

    later = t0 + timedelta(hours=2)
    (run,) = run_all(factory, [ACME], fetcher_for(net), settings, clock=lambda: later)
    assert run.status == "skipped" and len(net.calls) == 1  # no second request
    with factory() as s:
        assert snapshot == {
            p.external_id: (p.first_seen_at, p.last_seen_at, p.content_hash, p.closed_at)
            for p in s.scalars(select(Posting))
        }

    (forced,) = run_all(
        factory, [ACME], fetcher_for(net), settings, clock=lambda: later, force=True
    )
    assert len(net.calls) == 2 and (forced.new, forced.updated, forced.closed) == (0, 0, 0)
    assert count(factory, Posting) == 3  # idempotent: same rows, only last_seen_at advanced


def test_crash_after_save_replays_saved_bytes_without_network(
    factory: sessionmaker[Session],
    net: Net,
    fetcher_for: FetcherFor,
    settings: Settings,
    t0: datetime,
) -> None:
    run_all(factory, [ACME], fetcher_for(net), settings, clock=lambda: t0)
    with factory() as s:  # simulate a crash that lost the DB side but kept today's raw file
        for model in (Posting, IngestionRun):
            for row in s.scalars(select(model)):
                s.delete(row)
        s.commit()

    def boom(req: httpx.Request) -> httpx.Response:
        raise AssertionError("must not hit the network when today's raw file exists")

    (run,) = run_all(
        factory, [ACME], fetcher_for(boom), settings, clock=lambda: t0 + timedelta(hours=1)
    )
    assert run.status == "ok" and run.new == 3 and count(factory, Posting) == 3


def test_http_failure_is_recorded_and_closes_nothing(
    factory: sessionmaker[Session],
    net: Net,
    fetcher_for: FetcherFor,
    settings: Settings,
    t0: datetime,
) -> None:
    run_all(factory, [ACME], fetcher_for(net), settings, clock=lambda: t0)
    net.gh_status = 500
    (run,) = run_all(factory, [ACME], fetcher_for(net), settings, clock=lambda: t0 + DAY)
    assert (run.status, run.http_status, run.failed, run.closed) == ("failed", 500, 1, 0)
    assert run.error == "HTTP 500"
    with factory() as s:
        assert all(p.closed_at is None for p in s.scalars(select(Posting)))


def test_404_board_is_failed_and_saves_no_raw_file(
    factory: sessionmaker[Session],
    net: Net,
    fetcher_for: FetcherFor,
    settings: Settings,
    t0: datetime,
) -> None:
    net.gh_status = 404
    (run,) = run_all(factory, [ACME], fetcher_for(net), settings, clock=lambda: t0)
    assert run.status == "failed" and run.http_status == 404 and run.raw_path is None
    assert not list(settings.raw_dir.rglob("*.json.gz")) and count(factory, Posting) == 0


def test_garbage_200_response_is_not_saved_as_raw(
    factory: sessionmaker[Session], fetcher_for: FetcherFor, settings: Settings, t0: datetime
) -> None:
    fetcher = fetcher_for(lambda r: httpx.Response(200, content=b"<html>maintenance</html>"))
    (run,) = run_all(factory, [ACME], fetcher, settings, clock=lambda: t0)
    assert run.status == "failed" and "ParseError" in (run.error or "")
    assert not list(settings.raw_dir.rglob("*.json.gz"))


def test_empty_board_response_is_guarded_not_mass_closed(
    factory: sessionmaker[Session],
    net: Net,
    fetcher_for: FetcherFor,
    settings: Settings,
    t0: datetime,
) -> None:
    run_all(factory, [ACME], fetcher_for(net), settings, clock=lambda: t0)
    net.gh = json.dumps({"jobs": []}).encode()
    (run,) = run_all(factory, [ACME], fetcher_for(net), settings, clock=lambda: t0 + DAY)
    assert (run.status, run.closed, run.skipped_by_guard) == ("guarded", 0, 3)
    assert "empty snapshot" in (run.error or "")
    with factory() as s:
        assert all(p.closed_at is None for p in s.scalars(select(Posting)))


def test_posting_removed_next_day_is_closed_with_correct_times(
    factory: sessionmaker[Session],
    net: Net,
    fetcher_for: FetcherFor,
    settings: Settings,
    t0: datetime,
) -> None:
    run_all(factory, [ACME], fetcher_for(net), settings, clock=lambda: t0)
    jobs = json.loads(net.gh)["jobs"]
    net.gh = json.dumps({"jobs": jobs[:2]}).encode()  # 2 of 3 kept: not a >50% drop
    (run,) = run_all(factory, [ACME], fetcher_for(net), settings, clock=lambda: t0 + DAY)
    assert (run.status, run.closed) == ("ok", 1)
    with factory() as s:
        gone = s.scalars(select(Posting).where(Posting.external_id == "1003")).one()
        kept = s.scalars(select(Posting).where(Posting.external_id == "1001")).one()
    assert gone.closed_at == t0 + DAY and gone.last_seen_at == t0 and gone.first_seen_at == t0
    assert kept.closed_at is None and kept.last_seen_at == t0 + DAY


def test_one_failing_company_does_not_stop_the_others(
    factory: sessionmaker[Session],
    net: Net,
    fetcher_for: FetcherFor,
    settings: Settings,
    t0: datetime,
) -> None:
    net.gh_status = 503
    runs = run_all(factory, [ACME, BETA], fetcher_for(net), settings, clock=lambda: t0)
    assert [r.status for r in runs] == ["failed", "ok"] and count(factory, Posting) == 2


def test_old_raw_files_are_pruned_after_a_run(
    factory: sessionmaker[Session],
    net: Net,
    fetcher_for: FetcherFor,
    settings: Settings,
    t0: datetime,
) -> None:
    run_all(factory, [ACME], fetcher_for(net), settings, clock=lambda: t0)
    later = t0 + 20 * DAY
    run_all(factory, [ACME], fetcher_for(net), settings, clock=lambda: later)
    names = sorted(p.name[:10] for p in settings.raw_dir.rglob("*.json.gz"))
    assert names == [later.date().isoformat()]  # retention is 14 days; day-0 file is gone


# ---- CLI with the network mocked
def test_cli_run_and_clean_raw(
    tmp_path: Path,
    net: Net,
    fetcher_for: FetcherFor,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from shortlist_ml.db.models import Base

    db = f"sqlite:///{tmp_path / 'cli.db'}"
    settings = Settings(
        database_url=db,
        raw_dir=tmp_path / "raw",
        companies_file=tmp_path / "companies.yaml",
        request_interval_s=0.0,
    )
    Base.metadata.create_all(make_engine(db))
    settings.companies_file.write_text(
        "- {name: Acme, ats: greenhouse, board_token: acme}\n- {name: Beta, ats: lever, board_token: beta}\n"
    )
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "_fetcher", lambda: fetcher_for(net))

    assert cli.main(["run"]) == 0
    out = capsys.readouterr().out
    assert "Acme" in out and "Beta" in out and out.count(" ok ") == 2

    assert cli.main(["run", "--company", "acme"]) == 0  # same-day rerun
    assert " skipped " in capsys.readouterr().out and len(net.calls) == 2

    assert cli.main(["run", "--company", "nope"]) == 2

    net.gh_status = 500
    assert (
        cli.main(["run", "--force", "--company", "acme"]) == 1
    )  # a failed fetch => nonzero exit for cron

    assert cli.main(["clean-raw", "--dry-run"]) == 0
    assert "would delete 0" in capsys.readouterr().out


def test_report_counts_and_runs(
    factory: sessionmaker[Session],
    net: Net,
    fetcher_for: FetcherFor,
    settings: Settings,
    t0: datetime,
) -> None:
    from shortlist_ml.ingest.report import build_report

    run_all(factory, [ACME, BETA], fetcher_for(net), settings, clock=lambda: t0)
    with factory() as s:
        text = build_report(s, now=t0)
    # Synthetic Greenhouse fixture: 1001 SF (entry, US), 1002 "Remote - US" (senior, US, remote),
    # 1003 NYC "Engineer I" (entry, US) -> 3 postings, 2 entry-level, 0 interns, 3 US, 0 unknown, 1 remote.
    assert "| Acme | greenhouse | 3 | 2 | 0 | 3 | 0 | 1 | 0 |" in text
    assert "| Beta | lever | 2 | 1 | 0 | 1 | 0 | 1 | 0 |" in text
    assert "| **Total** | | **5** |" in text
    assert (
        "| ok | 2 | 5 | 5 | 0 | 0 | 0 | 0 | 0 |" in text
    )  # runs, fetched, new, updated, reopened, closed, failed, guard


# ---- end-to-end close -> reopen through the whole pipeline (fetch -> raw file -> parse -> store -> run row)
def _gh_payload(jobs: list[dict], keep: list[int], edit: dict[int, str] | None = None) -> bytes:  # type: ignore[type-arg]
    chosen = []
    for j in jobs:
        if j["id"] in keep:
            j = dict(j)
            if edit and j["id"] in edit:
                j["content"] = edit[j["id"]]
            chosen.append(j)
    return json.dumps({"jobs": chosen}).encode()


def test_end_to_end_close_then_reopen(
    factory: sessionmaker[Session],
    net: Net,
    fetcher_for: FetcherFor,
    settings: Settings,
    t0: datetime,
) -> None:
    jobs = json.loads(net.gh)["jobs"]  # ids 1001, 1002, 1003
    day1, day2, day3 = t0, t0 + DAY, t0 + 2 * DAY

    (r1,) = run_all(factory, [ACME], fetcher_for(net), settings, clock=lambda: day1)
    assert (r1.new, r1.closed, r1.reopened) == (3, 0, 0)

    # Day 2: posting 1003 disappears from the board (2 of 3 kept: not a >50% drop, so it is trusted).
    net.gh = _gh_payload(jobs, [1001, 1002])
    (r2,) = run_all(factory, [ACME], fetcher_for(net), settings, clock=lambda: day2)
    assert (r2.status, r2.closed, r2.reopened, r2.updated) == ("ok", 1, 0, 0)
    with factory() as s:
        p = s.scalars(select(Posting).where(Posting.external_id == "1003")).one()
        assert p.closed_at == day2 and p.last_seen_at == day1 and p.first_seen_at == day1

    # Day 3: it comes back unchanged -> reopened, and NOT counted as an edit.
    net.gh = _gh_payload(jobs, [1001, 1002, 1003])
    (r3,) = run_all(factory, [ACME], fetcher_for(net), settings, clock=lambda: day3)
    assert (r3.status, r3.reopened, r3.updated, r3.closed, r3.new) == ("ok", 1, 0, 0, 0)
    with factory() as s:
        p = s.scalars(select(Posting).where(Posting.external_id == "1003")).one()
        assert p.closed_at is None  # reopened
        assert p.first_seen_at == day1 and p.last_seen_at == day3
        assert p.updated_at is None  # reopening is not a content edit
        assert s.scalar(select(func.count()).select_from(Posting)) == 3  # same row, no duplicate


def test_end_to_end_reopen_with_an_edit_counts_both(
    factory: sessionmaker[Session],
    net: Net,
    fetcher_for: FetcherFor,
    settings: Settings,
    t0: datetime,
) -> None:
    jobs = json.loads(net.gh)["jobs"]
    run_all(factory, [ACME], fetcher_for(net), settings, clock=lambda: t0)
    net.gh = _gh_payload(jobs, [1001, 1002])
    run_all(factory, [ACME], fetcher_for(net), settings, clock=lambda: t0 + DAY)
    net.gh = _gh_payload(
        jobs, [1001, 1002, 1003], edit={1003: "&lt;p&gt;Rewritten description.&lt;/p&gt;"}
    )
    (r3,) = run_all(factory, [ACME], fetcher_for(net), settings, clock=lambda: t0 + 2 * DAY)
    assert (r3.reopened, r3.updated) == (1, 1)
    with factory() as s:
        p = s.scalars(select(Posting).where(Posting.external_id == "1003")).one()
        assert p.closed_at is None and p.updated_at == t0 + 2 * DAY
