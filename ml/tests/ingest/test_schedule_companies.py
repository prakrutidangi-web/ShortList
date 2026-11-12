from datetime import UTC, datetime, time
from pathlib import Path

import pytest

from shortlist_ml.ingest.companies import load_companies
from shortlist_ml.ingest.schedule import next_run_at


def test_next_run_is_today_if_still_ahead_else_tomorrow() -> None:
    # 06:00 Phoenix == 13:00 UTC (no DST in Phoenix)
    before = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)
    after = datetime(2026, 11, 12, 13, 0, tzinfo=UTC)
    assert next_run_at(before, time(6, 0), "America/Phoenix") == datetime(
        2026, 11, 12, 13, 0, tzinfo=UTC
    )
    assert next_run_at(after, time(6, 0), "America/Phoenix") == datetime(
        2026, 11, 13, 13, 0, tzinfo=UTC
    )


def test_load_companies_validates(tmp_path: Path) -> None:
    ok = tmp_path / "ok.yaml"
    ok.write_text(
        "- {name: Acme, ats: greenhouse, board_token: acme}\n- {name: Beta, ats: lever, board_token: beta-co}\n"
    )
    assert [c.board_token for c in load_companies(ok)] == ["acme", "beta-co"]
    for bad in (
        "- {name: A, ats: workday, board_token: a}",
        "- {name: A, ats: lever, board_token: '../x'}",
        "- {name: A, ats: lever}",
        "- {name: A, ats: lever, board_token: a}\n- {name: B, ats: lever, board_token: a}",
        "not: a list",
    ):
        p = tmp_path / "bad.yaml"
        p.write_text(bad)
        with pytest.raises(ValueError):
            load_companies(p)
