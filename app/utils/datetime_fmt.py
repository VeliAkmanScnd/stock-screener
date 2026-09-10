"""UTC datetime serialization for JSON APIs."""

from __future__ import annotations

from datetime import datetime, timezone


def utc_iso(dt: datetime | None) -> str | None:
    """ISO-8601 UTC string with Z suffix (JS parses correctly as UTC)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + "Z"
