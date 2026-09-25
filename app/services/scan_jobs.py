"""In-memory scan job progress (polled by the UI during long BIST scans)."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from app.database import SessionLocal

ProgressCallback = Callable[[str, int, int, str], None]


def _attach_telegram(result: dict[str, Any], *, notify: bool) -> dict[str, Any]:
    """Send manual-scan results to Telegram when requested and .env is configured."""
    from app.services.telegram_service import send_telegram_scan_result, telegram_configured

    if not notify:
        result["telegram_sent"] = False
        result["telegram_skipped"] = True
        result["telegram_error"] = None
        return result
    if not telegram_configured():
        result["telegram_sent"] = False
        result["telegram_error"] = (
            "Telegram yapılandırılmamış (.env: TELEGRAM_BOT_TOKEN ve TELEGRAM_CHAT_ID)"
        )
        return result
    try:
        name = result.get("pine_label") or (
            f"{result.get('universe') or 'tarama'} {result.get('timeframe') or ''}".strip()
        )
        send_telegram_scan_result(
            name=str(name),
            universe=str(result.get("universe") or ""),
            timeframe=str(result.get("timeframe") or ""),
            match_count=int(result.get("count") or 0),
            tv_list_text=str(result.get("tradingview_text") or ""),
            filename="tv_scan.txt",
        )
        result["telegram_sent"] = True
        result["telegram_error"] = None
    except Exception as exc:
        result["telegram_sent"] = False
        result["telegram_error"] = str(exc)
    return result


@dataclass
class ScanJob:
    id: str
    status: str = "running"  # running | done | error
    progress: int = 0
    phase: str = "starting"
    message: str = "Tarama başlatılıyor…"
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


_jobs: dict[str, ScanJob] = {}
_lock = threading.Lock()


def _get(job_id: str) -> ScanJob | None:
    with _lock:
        return _jobs.get(job_id)


def _update(job_id: str, **kwargs: Any) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        for key, value in kwargs.items():
            setattr(job, key, value)


def job_to_dict(job: ScanJob) -> dict[str, Any]:
    return {
        "job_id": job.id,
        "status": job.status,
        "progress": job.progress,
        "phase": job.phase,
        "message": job.message,
        "result": job.result,
        "error": job.error,
    }


def get_scan_job(job_id: str) -> dict[str, Any] | None:
    job = _get(job_id)
    return job_to_dict(job) if job else None


def make_progress_callback(job_id: str) -> ProgressCallback:
    def report(phase: str, done: int, total: int, detail: str = "") -> None:
        if total <= 0:
            pct = 0
        elif phase == "downloading":
            pct = int(min(70, max(0, (done / total) * 70)))
        elif phase == "scanning":
            pct = 70 + int(min(30, max(0, (done / total) * 30)))
        else:
            pct = int(min(100, max(0, (done / total) * 100)))

        if phase == "downloading":
            msg = f"Veri indiriliyor {done}/{total}"
        elif phase == "scanning":
            msg = f"Taranıyor {done}/{total}"
        else:
            msg = detail or "Tarama…"

        if detail:
            msg += f" — {detail}"
        _update(job_id, progress=pct, phase=phase, message=msg)

    return report


def start_scan_job(body: dict[str, Any]) -> str:
    job_id = str(uuid.uuid4())
    with _lock:
        _jobs[job_id] = ScanJob(id=job_id)
        # Keep memory bounded — drop jobs older than ~50 entries
        if len(_jobs) > 50:
            oldest = sorted(_jobs.values(), key=lambda j: j.created_at)
            for old in oldest[: len(_jobs) - 50]:
                _jobs.pop(old.id, None)

    def _run() -> None:
        db = SessionLocal()
        try:
            from app.services.scan_executor import execute_scan_config

            progress = make_progress_callback(job_id)
            result = execute_scan_config(body, db, progress_callback=progress)
            result = _attach_telegram(result, notify=bool(body.get("notify_telegram", True)))
            _update(
                job_id,
                status="done",
                progress=100,
                phase="done",
                message="Tamamlandı",
                result=result,
            )
        except Exception as exc:
            _update(
                job_id,
                status="error",
                phase="error",
                message=str(exc),
                error=str(exc),
            )
        finally:
            db.close()

    threading.Thread(target=_run, name=f"scan-{job_id[:8]}", daemon=True).start()
    return job_id
