"""Migrations against a FRESH, empty Postgres database (pgvector image). Needs `make test-db`."""

from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from shortlist_ml.db.models import Base

pytestmark = pytest.mark.db
REPO = Path(__file__).resolve().parents[3]


def _cfg(url: str) -> Config:
    cfg = Config(str(REPO / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def test_upgrade_fresh_db_matches_models_and_downgrades(scratch_pg_url: str) -> None:
    command.upgrade(_cfg(scratch_pg_url), "head")
    engine = create_engine(scratch_pg_url)
    try:
        tables = set(inspect(engine).get_table_names())
        assert {"users", "companies", "postings", "ingestion_runs", "alembic_version"} <= tables
        with engine.connect() as conn:
            assert conn.execute(text("SELECT id FROM users")).scalars().all() == [
                1
            ]  # local user seeded
            assert (
                conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")).scalar()
                == 1
            )
            # The migration and the SQLAlchemy models must not drift apart.
            diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
        assert diff == [], f"models and migration differ: {diff}"
    finally:
        engine.dispose()

    command.downgrade(_cfg(scratch_pg_url), "base")
    engine = create_engine(scratch_pg_url)
    try:
        assert set(inspect(engine).get_table_names()) == {"alembic_version"}
    finally:
        engine.dispose()
    command.upgrade(_cfg(scratch_pg_url), "head")  # and it can go up again
