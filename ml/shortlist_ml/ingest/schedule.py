"""Tiny built-in daily scheduler (ADR 0003): sleep until HH:MM in the configured timezone, run, repeat.

Prefer plain cron if you have it; this exists for the optional compose service.
"""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo


def next_run_at(now: datetime, at: time, tz: str) -> datetime:
    """Next occurrence of local wall-clock time `at` strictly after `now` (aware datetime)."""
    zone = ZoneInfo(tz)
    local = now.astimezone(zone)
    candidate = datetime.combine(local.date(), at, tzinfo=zone)
    if candidate <= local:
        candidate = datetime.combine(local.date() + timedelta(days=1), at, tzinfo=zone)
    return candidate
