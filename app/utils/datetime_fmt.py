"""UTC datetime helpers for storage + JSON APIs."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def utc_now() -> datetime:
    """Timezone-aware UTC now."""
    return datetime.now(timezone.utc)


def utc_now_naive() -> datetime:
    """Naive UTC now for SQLite DateTime columns (always store UTC)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def as_utc(dt: datetime | None) -> datetime | None:
    """Normalize any datetime to timezone-aware UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        # DB naive values are UTC by convention.
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def as_utc_naive(dt: datetime | None) -> datetime | None:
    """Normalize to naive UTC for SQLite writes."""
    aware = as_utc(dt)
    return None if aware is None else aware.replace(tzinfo=None)


def utc_iso(dt: datetime | None) -> str | None:
    """ISO-8601 UTC string with Z suffix (JS parses correctly as UTC)."""
    aware = as_utc(dt)
    if aware is None:
        return None
    return aware.strftime("%Y-%m-%dT%H:%M:%S") + "Z"


def istanbul_now_label() -> str:
    now = utc_now().astimezone(ZoneInfo("Europe/Istanbul"))
    return now.strftime("%Y-%m-%d %H:%M:%S %z")
