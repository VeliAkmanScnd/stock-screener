"""In-memory scan job progress (polled by the UI during long BIST scans)."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from app.database import SessionLocal

ProgressCallback = Callable[[str, int, int, str], None]


def _attach_telegram(
    result: dict[str, Any],
    *,
    notify: bool,
    extra_chat_ids: str | None = None,
    extra_bot_token: str | None = None,
) -> dict[str, Any]:
    """Send manual-scan results to Telegram when requested and a bot token exists."""
    from app.config import TELEGRAM_BOT_TOKEN
    from app.services.telegram_service import send_telegram_scan_result

    if not notify:
        result["telegram_sent"] = False
        result["telegram_sent_count"] = 0
        result["telegram_skipped"] = True
        result["telegram_error"] = None
        return result
    bot_token = (extra_bot_token or TELEGRAM_BOT_TOKEN or "").strip() or None
    if not bot_token:
        result["telegram_sent"] = False
        result["telegram_sent_count"] = 0
        result["telegram_error"] = "Telegram yapılandırılmamış (.env veya tarama bot token)"
        return result
    try:
        name = result.get("pine_label") or (
            f"{result.get('universe') or 'tarama'} {result.get('timeframe') or ''}".strip()
        )
        sent = send_telegram_scan_result(
            name=str(name),
            universe=str(result.get("universe") or ""),
            timeframe=str(result.get("timeframe") or ""),
            match_count=int(result.get("count") or 0),
            tv_list_text=str(result.get("tradingview_text") or ""),
            filename="tv_scan.txt",
            results=list(result.get("results") or []),
            custom_source_universe=result.get("custom_source_universe"),
            extra_chat_ids=extra_chat_ids,
            bot_token=bot_token,
        )
        result["telegram_sent"] = sent > 0
        result["telegram_sent_count"] = int(sent or 0)
        result["telegram_error"] = None
    except Exception as exc:
        result["telegram_sent"] = False
        result["telegram_sent_count"] = 0
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
        pct, msg = _format_progress(phase, done, total, detail)
        _update(job_id, progress=pct, phase=phase, message=msg)

    return report


def _format_progress(phase: str, done: int, total: int, detail: str = "") -> tuple[int, str]:
    if total <= 0:
        pct = 0
    elif phase == "downloading":
        pct = int(min(70, max(0, (done / total) * 70)))
    elif phase == "scanning":
        pct = 70 + int(min(25, max(0, (done / total) * 25)))
    elif phase in ("notify", "dedupe", "saving"):
        pct = 95
    elif phase == "done":
        pct = 100
    else:
        pct = int(min(100, max(0, (done / total) * 100)))

    phase_tr = {
        "starting": "Başlatılıyor",
        "downloading": "Veri indiriliyor",
        "scanning": "Taranıyor",
        "dedupe": "Tekrarlar eleniyor",
        "notify": "Bildirimler",
        "saving": "Kaydediliyor",
        "queued": "Kuyrukta",
        "done": "Tamamlandı",
        "error": "Hata",
    }
    label = phase_tr.get(phase, phase or "Tarama")
    if phase == "downloading" and total > 0:
        msg = f"{label} {done}/{total}"
    elif phase == "scanning" and total > 0:
        msg = f"{label} {done}/{total}"
    else:
        msg = detail or label
    if detail and detail not in msg:
        msg = f"{msg} — {detail}"
    return pct, msg


# --- Scheduled-scan progress (keyed by scheduled_scan_id) ---

@dataclass
class ScheduleProgress:
    scheduled_id: int
    run_id: int | None = None
    name: str = ""
    status: str = "running"  # queued | running | done | error
    progress: int = 0
    phase: str = "starting"
    message: str = "Tarama başlatılıyor…"
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


_schedule_progress: dict[int, ScheduleProgress] = {}
_schedule_lock = threading.Lock()


def begin_schedule_progress(
    scheduled_id: int,
    *,
    run_id: int | None = None,
    name: str = "",
    queued: bool = False,
) -> None:
    with _schedule_lock:
        _schedule_progress[scheduled_id] = ScheduleProgress(
            scheduled_id=scheduled_id,
            run_id=run_id,
            name=name or f"#{scheduled_id}",
            status="queued" if queued else "running",
            progress=0,
            phase="queued" if queued else "starting",
            message="Kuyrukta bekliyor…" if queued else "Tarama başlatılıyor…",
        )


def update_schedule_progress(
    scheduled_id: int,
    *,
    progress: int | None = None,
    phase: str | None = None,
    message: str | None = None,
    status: str | None = None,
    run_id: int | None = None,
) -> None:
    with _schedule_lock:
        row = _schedule_progress.get(scheduled_id)
        if not row:
            return
        if progress is not None:
            row.progress = int(max(0, min(100, progress)))
        if phase is not None:
            row.phase = phase
        if message is not None:
            row.message = message
        if status is not None:
            row.status = status
        if run_id is not None:
            row.run_id = run_id
        row.updated_at = datetime.now(timezone.utc)


def make_schedule_progress_callback(scheduled_id: int) -> ProgressCallback:
    def report(phase: str, done: int, total: int, detail: str = "") -> None:
        pct, msg = _format_progress(phase, done, total, detail)
        update_schedule_progress(
            scheduled_id,
            progress=pct,
            phase=phase,
            message=msg,
            status="running",
        )

    return report


def finish_schedule_progress(
    scheduled_id: int,
    *,
    ok: bool = True,
    message: str | None = None,
) -> None:
    with _schedule_lock:
        row = _schedule_progress.get(scheduled_id)
        if not row:
            return
        row.status = "done" if ok else "error"
        row.progress = 100 if ok else row.progress
        row.phase = "done" if ok else "error"
        row.message = message or ("Tamamlandı" if ok else "Hata")
        row.updated_at = datetime.now(timezone.utc)


def clear_schedule_progress(scheduled_id: int) -> None:
    with _schedule_lock:
        _schedule_progress.pop(scheduled_id, None)


def get_schedule_progress(scheduled_id: int) -> dict[str, Any] | None:
    with _schedule_lock:
        row = _schedule_progress.get(scheduled_id)
        if not row:
            return None
        # Drop stale finished entries after a short while
        age = (datetime.now(timezone.utc) - row.updated_at).total_seconds()
        if row.status in ("done", "error") and age > 120:
            _schedule_progress.pop(scheduled_id, None)
            return None
        return {
            "scheduled_id": row.scheduled_id,
            "run_id": row.run_id,
            "name": row.name,
            "status": row.status,
            "progress": row.progress,
            "phase": row.phase,
            "message": row.message,
        }


def get_active_schedule_progress() -> dict[int, dict[str, Any]]:
    with _schedule_lock:
        now = datetime.now(timezone.utc)
        out: dict[int, dict[str, Any]] = {}
        stale: list[int] = []
        for sid, row in _schedule_progress.items():
            age = (now - row.updated_at).total_seconds()
            if row.status in ("done", "error") and age > 120:
                stale.append(sid)
                continue
            if row.status not in ("queued", "running") and age > 30:
                stale.append(sid)
                continue
            out[sid] = {
                "scheduled_id": row.scheduled_id,
                "run_id": row.run_id,
                "name": row.name,
                "status": row.status,
                "progress": row.progress,
                "phase": row.phase,
                "message": row.message,
            }
        for sid in stale:
            _schedule_progress.pop(sid, None)
        return out


def start_scan_job(body: dict[str, Any], user_id: int | None = None) -> str:
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
            if user_id:
                from app.services.signal_dedupe import apply_repeat_price_filter, scan_fingerprint

                result = apply_repeat_price_filter(
                    db,
                    result,
                    user_id=user_id,
                    fingerprint=scan_fingerprint(
                        user_id=user_id,
                        universe=str(result.get("universe") or body.get("universe") or ""),
                        timeframe=str(result.get("timeframe") or body.get("timeframe") or ""),
                        custom_source_universe=result.get("custom_source_universe")
                        or body.get("custom_source_universe"),
                        pine_script_id=body.get("pine_script_id"),
                    ),
                )
            result = _attach_telegram(
                result,
                notify=bool(body.get("notify_telegram", True)),
                extra_chat_ids=body.get("telegram_to"),
                extra_bot_token=body.get("telegram_bot_token"),
            )
            if user_id and result.get("results"):
                try:
                    from app.services.track_service import ingest_scan_results

                    label = result.get("pine_label") or "Manuel tarama"
                    ingested = ingest_scan_results(
                        db,
                        user_id=user_id,
                        payload=result,
                        source_type="manual",
                        source_label=str(label),
                    )
                    result["track_added"] = ingested
                except Exception as exc:
                    result["track_added"] = 0
                    result["track_error"] = str(exc)
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
