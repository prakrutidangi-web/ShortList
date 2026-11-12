from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator[datetime]):
    """timestamptz that always round-trips as an aware UTC datetime (also on SQLite in tests).

    Naive datetimes are rejected: the first_seen/last_seen/closed timestamps feed time-based
    train/eval splits, so silent timezone ambiguity would be a leakage risk.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime passed to UTCDateTime column")
        return value.astimezone(UTC)

    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        dt: datetime = value
        return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


EMBEDDING_DIM = 384  # bge-small-en-v1.5


class EmbeddingVector(TypeDecorator[list[float]]):
    """pgvector `vector(384)` on PostgreSQL; a JSON list elsewhere (SQLite in unit tests).

    Values are plain list[float] in Python. Similarity search on PostgreSQL uses the `<=>` operator in SQL;
    on other databases the retrieval code falls back to an exact in-Python scan (see recommend/retrieve.py).
    """

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> Any:
        if dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector

            return dialect.type_descriptor(Vector(EMBEDDING_DIM))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value: Any, dialect: Dialect) -> Any:
        return None if value is None else [float(x) for x in value]

    def process_result_value(self, value: Any, dialect: Dialect) -> list[float] | None:
        return None if value is None else [float(x) for x in value]
