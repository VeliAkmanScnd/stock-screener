"""UTC datetime helpers for storage + JSON APIs."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_ISTANBUL = ZoneInfo("Europe/Istanbul")
_WALL_WARNED = False


def _wall_clock_as_istanbul() -> bool:
    """Opt-in only: treat the Windows local face as Europe/Istanbul.

    Default is off. With 'Set time automatically' ON, UTC is correct even when
    the Windows timezone (and local face) is not Istanbul — e.g. VPS shows
    00:49 while Istanbul is 10:49. Schedules must use raw UTC → Europe/Istanbul.
    """
    return os.getenv("TRADELAB_WALL_CLOCK_AS_ISTANBUL", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def utc_now() -> datetime:
    """Timezone-aware UTC now (raw system / NTP clock)."""
    return datetime.now(timezone.utc)


def effective_utc_now() -> datetime:
    """UTC now for schedules and APIs.

    Trust system UTC by default (auto time). CronTriggers already use
    Europe/Istanbul, so a wrong Windows *display* timezone does not matter.

    Set TRADELAB_WALL_CLOCK_AS_ISTANBUL=1 only if the VPS clock face was
    manually set to Istanbul while Windows TZ stays wrong (UTC then drifts).
    """
    global _WALL_WARNED
    raw_utc = datetime.now(timezone.utc)
    if not _wall_clock_as_istanbul():
        return raw_utc

    istanbul_face = raw_utc.astimezone(_ISTANBUL).replace(tzinfo=None)
    local_face = datetime.now().replace(tzinfo=None)
    drift_sec = (local_face - istanbul_face).total_seconds()
    if abs(drift_sec) <= 1800:
        return raw_utc

    corrected = local_face.replace(tzinfo=_ISTANBUL).astimezone(timezone.utc)
    if not _WALL_WARNED:
        _WALL_WARNED = True
        logger.warning(
            "TRADELAB_WALL_CLOCK_AS_ISTANBUL: local=%s istanbul_from_utc=%s drift=%ss — "
            "yerel yüz Europe/Istanbul kabul edildi.",
            local_face.isoformat(timespec="seconds"),
            istanbul_face.isoformat(timespec="seconds"),
            int(drift_sec),
        )
    return corrected


def effective_utc_now_naive() -> datetime:
    return effective_utc_now().replace(tzinfo=None)


def utc_now_naive() -> datetime:
    """Naive UTC now for SQLite DateTime columns (always store UTC)."""
    return effective_utc_now_naive()


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
    now = effective_utc_now().astimezone(_ISTANBUL)
    return now.strftime("%Y-%m-%d %H:%M:%S %z")


def clock_skew_info() -> dict:
    """Compare Windows local face vs Istanbul-from-UTC (informational).

    A mismatch is normal when the VPS timezone cannot be changed; it does not
    break schedules as long as automatic time (correct UTC) stays enabled.
    """
    raw_utc = datetime.now(timezone.utc)
    istanbul_from_utc = raw_utc.astimezone(_ISTANBUL)
    local_face = datetime.now().replace(tzinfo=None)
    istanbul_face = istanbul_from_utc.replace(tzinfo=None)
    drift_sec = int((local_face - istanbul_face).total_seconds())
    mismatch = abs(drift_sec) > 1800
    wall_mode = _wall_clock_as_istanbul()
    return {
        # Legacy key: only true when wall-as-Istanbul mode is actively correcting.
        "skewed": bool(wall_mode and mismatch),
        "windows_tz_mismatch": mismatch,
        "drift_seconds": drift_sec,
        "local_face": local_face.strftime("%Y-%m-%d %H:%M:%S"),
        "istanbul_from_utc": istanbul_from_utc.strftime("%Y-%m-%d %H:%M:%S %z"),
        "effective_istanbul": effective_utc_now().astimezone(_ISTANBUL).strftime(
            "%Y-%m-%d %H:%M:%S %z"
        ),
        "mode": "wall_as_istanbul" if wall_mode else "trust_utc",
        "hint": (
            "Windows yerel saat ≠ İstanbul; sorun değil. Otomatik saati açık tutun. "
            "Planlar UTC → Europe/Istanbul ile çalışır (TZ değiştirmeniz gerekmez)."
            if mismatch and not wall_mode
            else (
                "TRADELAB_WALL_CLOCK_AS_ISTANBUL aktif — yerel yüz İstanbul kabul ediliyor."
                if wall_mode and mismatch
                else ""
            )
        ),
    }
