"""Execute scheduled scans and persist results."""

from __future__ import annotations

import json
import logging
import queue
import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import ScanRun, ScheduledScan, SessionLocal
from app.services.email_service import send_tv_list_email
from app.services.telegram_service import send_telegram_scan_result, telegram_configured
from app.services.scan_executor import execute_scan_config
from app.services.schedule_helpers import min_run_interval_seconds

logger = logging.getLogger(__name__)

_scan_lock = threading.Lock()
_scan_queue: queue.Queue[int] = queue.Queue()
_queued_ids: set[int] = set()
_queue_lock = threading.Lock()

_RACE_WINDOW = timedelta(minutes=3)
_STALE_RUNNING = timedelta(hours=2)


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _duplicate_skip_reason(
    db: Session,
    sched: ScheduledScan,
    *,
    force: bool,
) -> str | None:
    if force:
        return None

    now = datetime.now(timezone.utc)
    running = (
        db.query(ScanRun)
        .filter(
            ScanRun.scheduled_scan_id == sched.id,
            ScanRun.status == "running",
        )
        .order_by(ScanRun.started_at.desc())
        .first()
    )
    if running and running.started_at:
        age = now - _as_utc(running.started_at)
        if age < _STALE_RUNNING:
            return f"already running (run #{running.id})"

    recent = (
        db.query(ScanRun)
        .filter(
            ScanRun.scheduled_scan_id == sched.id,
            ScanRun.started_at >= now - _RACE_WINDOW,
        )
        .first()
    )
    if recent:
        return f"started recently (run #{recent.id})"

    if sched.last_run_at:
        since = now - _as_utc(sched.last_run_at)
        min_gap = timedelta(seconds=min_run_interval_seconds(sched.schedule_type))
        if since < min_gap:
            return f"last run {int(since.total_seconds())}s ago"

    return None


def _enqueue_scheduled_scan(scheduled_id: int) -> None:
    with _queue_lock:
        if scheduled_id in _queued_ids:
            logger.info("Scheduled scan %s already queued", scheduled_id)
            return
        _queued_ids.add(scheduled_id)
        _scan_queue.put(scheduled_id)
    logger.info("Scheduled scan %s queued — another scan is running", scheduled_id)


def _dequeue_next() -> int | None:
    with _queue_lock:
        try:
            scheduled_id = _scan_queue.get_nowait()
        except queue.Empty:
            return None
        _queued_ids.discard(scheduled_id)
        return scheduled_id


def _run_next_queued() -> None:
    next_id = _dequeue_next()
    if next_id is not None:
        threading.Thread(target=run_scheduled_scan, args=(next_id,), daemon=True).start()


def run_scheduled_scan(scheduled_id: int, *, force: bool = False) -> None:
    """Background job entry point."""
    if not _scan_lock.acquire(blocking=False):
        _enqueue_scheduled_scan(scheduled_id)
        return

    db = SessionLocal()
    run_row: ScanRun | None = None
    try:
        db.execute(text("BEGIN IMMEDIATE"))
        sched = db.query(ScheduledScan).filter(ScheduledScan.id == scheduled_id).first()
        if not sched or not sched.enabled:
            db.rollback()
            return

        skip = _duplicate_skip_reason(db, sched, force=force)
        if skip:
            logger.info("Skipping scheduled scan %s (%s)", scheduled_id, skip)
            db.rollback()
            return

        run_row = ScanRun(
            scheduled_scan_id=sched.id,
            started_at=datetime.now(timezone.utc),
            status="running",
        )
        db.add(run_row)
        db.commit()
        db.refresh(run_row)

        config = json.loads(sched.config_json)
        payload = execute_scan_config(config, db)

        tv_text = payload.get("tradingview_text") or ""
        match_count = int(payload.get("count") or 0)
        email_sent = False
        notify_errors: list[str] = []

        if sched.email_to:
            try:
                subject = (
                    f"TradeLABtr tarama: {sched.name} — {match_count} eşleşme"
                )
                body = (
                    f"Zamanlanmış tarama tamamlandı.\n\n"
                    f"Ad: {sched.name}\n"
                    f"Evren: {payload.get('universe')}\n"
                    f"Zaman dilimi: {payload.get('timeframe')}\n"
                    f"Eşleşme: {match_count}\n\n"
                    f"TradingView sembol listesi ekte (.txt).\n"
                )
                if not tv_text.strip():
                    body += "\n(Bu turda eşleşme yok — ek boş liste.)\n"
                send_tv_list_email(
                    to_address=sched.email_to,
                    subject=subject,
                    body_text=body,
                    tv_list_text=tv_text or "# no matches\n",
                    filename=f"tv_{sched.id}_{run_row.id}.txt",
                )
                email_sent = True
            except Exception as exc:
                notify_errors.append(f"e-posta: {exc}")
                logger.exception("Email failed for schedule %s", scheduled_id)

        telegram_sent = False
        notify_telegram = bool(getattr(sched, "notify_telegram", True))
        if notify_telegram and (
            telegram_configured() or (getattr(sched, "telegram_to", None) or "").strip()
        ):
            try:
                sent = send_telegram_scan_result(
                    name=sched.name,
                    universe=str(payload.get("universe") or ""),
                    timeframe=str(payload.get("timeframe") or ""),
                    match_count=match_count,
                    tv_list_text=tv_text or "",
                    extra_chat_ids=getattr(sched, "telegram_to", None),
                    filename=f"tv_{sched.id}_{run_row.id}.txt",
                    results=list(payload.get("results") or []),
                    custom_source_universe=payload.get("custom_source_universe"),
                )
                telegram_sent = sent > 0 or match_count == 0
            except Exception as exc:
                notify_errors.append(f"telegram: {exc}")
                logger.exception("Telegram failed for schedule %s", scheduled_id)

        notify_error = " | ".join(notify_errors) if notify_errors else None
        run_row.finished_at = datetime.now(timezone.utc)
        run_row.status = "success"
        run_row.match_count = match_count
        run_row.results_json = json.dumps(payload, ensure_ascii=False)
        run_row.tv_list_text = tv_text
        run_row.email_sent = email_sent
        run_row.error_message = notify_error

        sched.last_run_at = run_row.finished_at
        if notify_error and not email_sent and not telegram_sent:
            sched.last_status = "success_no_email"
        elif notify_error and not email_sent:
            sched.last_status = "success_no_email"
        elif notify_error and not telegram_sent:
            sched.last_status = "success_no_telegram"
        else:
            sched.last_status = "success"
        sched.last_match_count = match_count
        sched.last_error = notify_error
        db.commit()
        logger.info(
            "Scheduled scan %s done: %s matches, email=%s telegram=%s",
            scheduled_id,
            match_count,
            email_sent,
            telegram_sent,
        )

        from app.services.track_service import ingest_scan_results

        ingest_scan_results(
            db,
            user_id=sched.user_id,
            payload=payload,
            source_type="scheduled",
            source_label=sched.name,
            scheduled_scan_id=sched.id,
            scan_run_id=run_row.id if run_row else None,
            schedule_type=sched.schedule_type,
        )
    except Exception as exc:
        logger.exception("Scheduled scan %s failed", scheduled_id)
        if run_row:
            run_row.finished_at = datetime.now(timezone.utc)
            run_row.status = "error"
            run_row.error_message = str(exc)
            db.commit()
        sched = db.query(ScheduledScan).filter(ScheduledScan.id == scheduled_id).first()
        if sched:
            sched.last_run_at = datetime.now(timezone.utc)
            sched.last_status = "error"
            sched.last_error = str(exc)
            db.commit()
    finally:
        db.close()
        _scan_lock.release()
        _run_next_queued()
