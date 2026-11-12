from collections.abc import Callable

from sqlalchemy import create_engine, text

from shortlist_api.config import get_settings

DbCheck = Callable[[], bool]


def check_db() -> bool:
    """Return True if Postgres answers `SELECT 1`. Never raises; no PII is logged."""
    engine = create_engine(
        get_settings().database_url, connect_args={"connect_timeout": 2}, pool_pre_ping=True
    )
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
    finally:
        engine.dispose()
