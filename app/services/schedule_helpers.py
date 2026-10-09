"""Parse and validate scheduled scan email lists and weekday selections."""

from __future__ import annotations

from datetime import datetime, timedelta

from apscheduler.triggers.cron import CronTrigger
from email_validator import EmailNotValidError, validate_email

WEEKDAY_LABELS = ("Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz")

# Canonical ids match scan timeframes. Old schedule_type names still accepted.
SCHEDULE_TYPE_ALIASES: dict[str, str] = {
    "hourly": "1h",
    "every_4h": "4h",
    "every_2h": "2h",
    "every_5m": "5m",
    "every_15m": "15m",
    "every_30m": "30m",
    "every_8h": "8h",
    "every_12h": "12h",
    "daily": "1d",
    "weekly": "1wk",
}
WINDOW_INTERVAL_MINUTES: dict[str, int] = {
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "2h": 120,
    "4h": 240,
    "8h": 480,
    "12h": 720,
}
CANONICAL_SCHEDULE_TYPES = frozenset({"1d", "1wk", *WINDOW_INTERVAL_MINUTES})
SCHEDULE_TYPES = CANONICAL_SCHEDULE_TYPES | frozenset(SCHEDULE_TYPE_ALIASES)


def normalize_schedule_type(schedule_type: str | None) -> str:
    raw = (schedule_type or "1d").strip().lower()
    return SCHEDULE_TYPE_ALIASES.get(raw, raw)


def is_window_schedule_type(schedule_type: str | None) -> bool:
    return normalize_schedule_type(schedule_type) in WINDOW_INTERVAL_MINUTES


def minute_step_cron(interval_minutes: int, phase: int = 0) -> str:
    if interval_minutes <= 0 or 60 % interval_minutes != 0:
        raise ValueError("Dakika adımı 60'ı tam bölmeli (5, 15, 30).")
    phase = int(phase) % interval_minutes
    return ",".join(str(m) for m in range(phase, 60, interval_minutes))


def parse_email_list(raw: str) -> list[str]:
    """Split semicolon-separated addresses and validate each."""
    if not raw or not raw.strip():
        return []
    out: list[str] = []
    for part in raw.split(";"):
        addr = part.strip()
        if not addr:
            continue
        try:
            validated = validate_email(addr, check_deliverability=False)
            out.append(validated.normalized)
        except EmailNotValidError as exc:
            raise ValueError(f"Geçersiz e-posta: {addr}") from exc
    return out


def normalize_email_storage(emails: list[str]) -> str:
    return "; ".join(emails)


def parse_weekdays_field(raw: str | None) -> list[int]:
    if not raw or not raw.strip():
        return []
    out: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        day = int(part)
        if day < 0 or day > 6:
            raise ValueError(f"Geçersiz gün: {day} (0=Pazartesi … 6=Pazar)")
        if day not in out:
            out.append(day)
    return sorted(out)


def weekdays_to_storage(days: list[int]) -> str:
    return ",".join(str(d) for d in sorted(set(days)))


def weekdays_to_cron(days: list[int]) -> str:
    return weekdays_to_storage(days)


def format_weekdays_label(days: list[int]) -> str:
    return ", ".join(WEEKDAY_LABELS[d] for d in sorted(days) if 0 <= d <= 6)


def min_run_interval_seconds(schedule_type: str) -> int:
    """Minimum gap between automatic runs (prevents duplicate cron triggers).

    Window schedules (5m/15m/…) rely on race-window + already-running checks instead:
    finish-time gaps skipped legitimate next slots when a scan took more than ~3 minutes.
    """
    stype = normalize_schedule_type(schedule_type)
    if stype in WINDOW_INTERVAL_MINUTES:
        return 0
    if stype == "1wk":
        return 6 * 24 * 3600
    return 23 * 3600


def hour_window_cron(start: int, end: int, *, step: int = 1) -> str:
    """APScheduler cron hour field for an inclusive local-time window."""
    if start > end:
        raise ValueError("Bitiş saati başlangıçtan önce olamaz.")
    if start == end:
        return str(start)
    if step <= 1:
        return f"{start}-{end}"
    return f"{start}-{end}/{step}"


def window_minute_bounds(hour: int, minute: int, end_hour: int) -> tuple[int, int]:
    """Inclusive local minute-of-day bounds. End uses the same minute as the start."""
    start = int(hour) * 60 + (int(minute) % 60)
    end = int(end_hour) * 60 + (int(minute) % 60)
    if end < start:
        raise ValueError("Bitiş saati başlangıçtan önce olamaz.")
    return start, end


def is_window_slot(local_dt: datetime, start_mod: int, end_mod: int, interval: int) -> bool:
    """True when local_dt is an interval tick inside the inclusive clock window."""
    if interval <= 0:
        return False
    mod = local_dt.hour * 60 + local_dt.minute
    if mod < start_mod or mod > end_mod:
        return False
    return (mod - start_mod) % interval == 0


class AlignedWindowTrigger(CronTrigger):
    """Cron wake-ups trimmed to the inclusive start/end minute.

    A plain hour range plus minute list also fires before the start minute
    (15:00 when the window opens at 15:15) and after the end minute
    (23:30 and 23:45 when the window closes at 23:15).
    """

    def __init__(
        self,
        *,
        start_minute_of_day: int,
        end_minute_of_day: int,
        interval: int,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.start_minute_of_day = int(start_minute_of_day)
        self.end_minute_of_day = int(end_minute_of_day)
        self.interval = int(interval)

    def get_next_fire_time(self, previous_fire_time, now):
        prev = previous_fire_time
        probe = now
        for _ in range(5000):
            nxt = super().get_next_fire_time(prev, probe)
            if nxt is None:
                return None
            local = nxt.astimezone(self.timezone)
            if is_window_slot(
                local,
                self.start_minute_of_day,
                self.end_minute_of_day,
                self.interval,
            ):
                return nxt
            prev = nxt
            probe = nxt + timedelta(microseconds=1)
        return None
