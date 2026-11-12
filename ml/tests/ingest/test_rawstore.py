from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from shortlist_ml.ingest import rawstore


def test_save_roundtrip_and_naming(tmp_path: Path) -> None:
    now = datetime(2026, 11, 12, 3, 30, tzinfo=UTC)  # 20:30 on Nov 11 in Phoenix (UTC-7)
    path, sha = rawstore.save(
        tmp_path, "greenhouse", "acme", b'{"jobs": []}', now, "America/Phoenix"
    )
    assert path.name == "2026-11-11__033000Z.json.gz"  # local date, UTC time
    assert rawstore.read(path) == b'{"jobs": []}' and len(sha) == 64
    assert rawstore.latest_for_date(tmp_path, "greenhouse", "acme", date(2026, 11, 11)) == path
    assert rawstore.latest_for_date(tmp_path, "greenhouse", "acme", date(2026, 11, 12)) is None
    assert not list(tmp_path.rglob("*.tmp"))


def test_latest_picks_newest_of_the_day(tmp_path: Path) -> None:
    for hour in (1, 5):
        rawstore.save(
            tmp_path, "lever", "acme", b"[]", datetime(2026, 11, 12, hour, tzinfo=UTC), "UTC"
        )
    latest = rawstore.latest_for_date(tmp_path, "lever", "acme", date(2026, 11, 12))
    assert latest is not None and "050000Z" in latest.name


def test_prune_keeps_recent_and_ignores_foreign_files(tmp_path: Path) -> None:
    for day in (1, 10, 11, 12):
        rawstore.save(
            tmp_path, "lever", "acme", b"[]", datetime(2026, 11, day, 12, tzinfo=UTC), "UTC"
        )
    foreign = tmp_path / "lever" / "acme" / "notes.json.gz"
    foreign.write_bytes(b"x")
    today = date(2026, 11, 12)
    assert len(rawstore.prune(tmp_path, 14, today, dry_run=True)) == 0
    dry = rawstore.prune(tmp_path, 2, today, dry_run=True)
    # The Nov 10 file sits exactly on the cutoff and is kept.
    assert [p.name[:10] for p in dry] == ["2026-11-01"]
    assert all(p.exists() for p in dry)
    rawstore.prune(tmp_path, 2, today)
    left = sorted(p.name[:10] for p in (tmp_path / "lever" / "acme").glob("2026*"))
    assert left == ["2026-11-10", "2026-11-11", "2026-11-12"] and foreign.exists()


@pytest.mark.parametrize("token", ["../etc", "a/b", "", ".hidden", "x y"])
def test_unsafe_board_tokens_rejected(tmp_path: Path, token: str) -> None:
    with pytest.raises(ValueError):
        rawstore.board_dir(tmp_path, "lever", token)
