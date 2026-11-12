from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from shortlist_ml.config import Settings, get_settings
from shortlist_ml.db.session import make_engine, make_session_factory
from shortlist_ml.embeddings.encoder import Encoder, get_encoder

LOCAL_USER_ID = 1  # single local user until Phase 5 accounts (ADR 0006)


@lru_cache
def _engine() -> Engine:
    return make_engine(get_settings().database_url)


@lru_cache
def _factory() -> sessionmaker[Session]:
    return make_session_factory(_engine())


def get_session() -> Iterator[Session]:
    with _factory()() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


@lru_cache
def get_cached_encoder() -> Encoder:
    """Loaded once per process (the model takes a few seconds to load)."""
    return get_encoder(get_settings())


def get_user_id() -> int:
    return LOCAL_USER_ID


def get_app_settings() -> Settings:
    return get_settings()
