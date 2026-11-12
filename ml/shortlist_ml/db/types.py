from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime
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
