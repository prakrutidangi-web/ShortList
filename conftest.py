import os
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from shortlist_ml.config import Settings
from shortlist_ml.db.models import Base
from shortlist_ml.ingest.http import Fetcher, RateLimiter

REPO = Path(__file__).resolve().parent
FIXTURES = REPO / "data" / "fixtures" / "synthetic"
T0 = datetime(2026, 11, 12, 14, 0, tzinfo=UTC)  # 07:00 in America/Phoenix


@contextmanager
def scratch_postgres_db() -> Iterator[str]:
    """Create an empty database on the dev Postgres server, yield its URL, always drop it."""
    if not os.environ.get("RUN_DB_TESTS"):
        pytest.skip("set RUN_DB_TESTS=1 with Postgres running (make test-db)")
    base = make_url(os.environ.get("DATABASE_URL") or Settings().database_url)
    name = f"shortlist_test_{uuid.uuid4().hex[:8]}"
    admin = create_engine(base, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        yield base.set(database=name).render_as_string(hide_password=False)
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture(params=["sqlite", pytest.param("postgres", marks=pytest.mark.db)])
def engine(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Engine]:
    """Store/run logic is exercised on SQLite (fast, no Docker) AND on real Postgres (-m db)."""
    if request.param == "sqlite":
        eng = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
        Base.metadata.create_all(eng)
        yield eng
        eng.dispose()
    else:
        with scratch_postgres_db() as url:
            eng = create_engine(url)
            with eng.begin() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            Base.metadata.create_all(eng)
            yield eng
            eng.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with Session(engine, expire_on_commit=False) as s:
        yield s


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(raw_dir=tmp_path / "raw", raw_retention_days=14, request_interval_s=0.0)


@pytest.fixture
def fetcher_for() -> Callable[[Callable[[httpx.Request], httpx.Response]], Fetcher]:
    """Build a Fetcher backed by an in-process mock transport: tests never touch the network."""

    def build(handler: Callable[[httpx.Request], httpx.Response]) -> Fetcher:
        client = httpx.Client(transport=httpx.MockTransport(handler))
        return Fetcher(client, RateLimiter(0.0, sleep=lambda _s: None), sleep=lambda _s: None)

    return build


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def t0() -> datetime:
    return T0


@pytest.fixture
def scratch_pg_url() -> Iterator[str]:
    with scratch_postgres_db() as url:
        yield url


@pytest.fixture
def real_fixtures_dir() -> Path:
    """Trimmed REAL postings recorded from the live APIs (see docs/data-sources.md)."""
    return REPO / "data" / "fixtures"
