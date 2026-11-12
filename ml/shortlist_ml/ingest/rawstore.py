"""Raw API responses on disk, gzipped, so any normalized row can be reproduced from source bytes.

Layout: <raw_dir>/<source>/<board_token>/<local-date>__<utc-HHMMSS>Z.json.gz
`local-date` is in the configured timezone (it defines "today" for the skip rule and retention).
"""

import gzip
import hashlib
import os
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

_NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})__(\d{6})Z\.json\.gz$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def board_dir(raw_dir: Path, source: str, board_token: str) -> Path:
    if not _TOKEN_RE.match(board_token) or ".." in board_token:
        raise ValueError(f"unsafe board token: {board_token!r}")
    return raw_dir / source / board_token


def save(
    raw_dir: Path, source: str, board_token: str, content: bytes, now: datetime, tz: str
) -> tuple[Path, str]:
    """Write atomically; returns (path, sha256 of the uncompressed bytes)."""
    directory = board_dir(raw_dir, source, board_token)
    directory.mkdir(parents=True, exist_ok=True)
    local_date = now.astimezone(ZoneInfo(tz)).date().isoformat()
    path = directory / f"{local_date}__{now.astimezone(UTC):%H%M%S}Z.json.gz"
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(gzip.compress(content))
    os.replace(tmp, path)
    return path, hashlib.sha256(content).hexdigest()


def read(path: Path) -> bytes:
    return gzip.decompress(path.read_bytes())


def latest_for_date(raw_dir: Path, source: str, board_token: str, day: date) -> Path | None:
    directory = board_dir(raw_dir, source, board_token)
    if not directory.is_dir():
        return None
    matches = sorted(
        p for p in directory.glob(f"{day.isoformat()}__*.json.gz") if _NAME_RE.match(p.name)
    )
    return matches[-1] if matches else None


def prune(raw_dir: Path, keep_days: int, today: date, *, dry_run: bool = False) -> list[Path]:
    """Delete raw files whose local date is older than `keep_days` days. Only files that match the
    naming scheme under raw_dir are ever touched. Returns the (would-be) deleted paths."""
    cutoff = today - timedelta(days=keep_days)
    doomed: list[Path] = []
    if not raw_dir.is_dir():
        return doomed
    for path in raw_dir.glob("*/*/*.json.gz"):
        m = _NAME_RE.match(path.name)
        if m and date.fromisoformat(m.group(1)) < cutoff:
            doomed.append(path)
    if not dry_run:
        for path in doomed:
            path.unlink()
    return sorted(doomed)
