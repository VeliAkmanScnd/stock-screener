"""Process / scheduler health for healthz + Özet dashboard."""

from __future__ import annotations

from datetime import datetime, timezone

from app.config import STORAGE_DIR
from app.utils.datetime_fmt import utc_iso

_STARTED_AT = datetime.now(timezone.utc)


def process_started_at() -> datetime:
    return _STARTED_AT


def _watchdog_tail() -> str | None:
    path = STORAGE_DIR / "watchdog.log"
    if not path.is_file():
        return None
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        return lines[-1] if lines else None
    except OSError:
        return None


def build_runtime_status() -> dict:
    from app.services.scheduler import scheduler_status

    sched = scheduler_status()
    started = _STARTED_AT
    now = datetime.now(timezone.utc)
    uptime_sec = max(0, int((now - started).total_seconds()))
    jobs = list(sched.get("jobs") or [])
    next_jobs = [j for j in jobs if j.get("next_run")]
    next_jobs.sort(key=lambda j: j.get("next_run") or "")
    next_at = next_jobs[0]["next_run"] if next_jobs else None

    return {
        "ok": True,
        "app": "TradeLABtr",
        "server": "up",
        "started_at": utc_iso(started),
        "uptime_seconds": uptime_sec,
        "scheduler_running": bool(sched.get("running")),
        "scheduler_jobs": int(sched.get("job_count") or 0),
        "next_job_at": next_at,
        "watchdog_last": _watchdog_tail(),
        "checked_at": utc_iso(now),
        "hint_if_down": (
            "ERR_CONNECTION_REFUSED = sunucu kapalı. VPS'te: "
            "git pull && .\\install-windows-task.ps1  veya  start-tradelab.bat"
        ),
    }
