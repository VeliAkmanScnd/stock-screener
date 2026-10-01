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
_STALE_RUNNING = timedelta(minutes=45)


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def cleanup_stale_running_scans(max_age: timedelta | None = None) -> int:
    """Mark orphan 'running' rows as error so schedules are not blocked after restart."""
    age_limit = max_age if max_age is not None else timedelta(minutes=15)
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        rows = (
            db.query(ScanRun)
            .filter(ScanRun.status == "running")
            .order_by(ScanRun.started_at.asc())
            .all()
        )
        fixed = 0
        for row in rows:
            started = _as_utc(row.started_at) if row.started_at else None
            if started is not None and (now - started) < age_limit:
                continue
            row.status = "error"
            row.finished_at = now
            row.error_message = "Kesildi: süreç yeniden başladı veya tarama takıldı"
            fixed += 1
            sched = (
                db.query(ScheduledScan)
                .filter(ScheduledScan.id == row.scheduled_scan_id)
                .first()
            )
            if sched and (sched.last_status or "") == "running":
                sched.last_status = "error"
                sched.last_error = row.error_message
                sched.last_run_at = now
        if fixed:
            db.commit()
            logger.warning("Cleared %s stale running ScanRun row(s)", fixed)
        return fixed
    except Exception:
        logger.exception("Failed to clear stale running scans")
        db.rollback()
        return 0
    finally:
        db.close()


def _duplicate_skip_reason(
    db: Session,
    sched: ScheduledScan,
    *,
    force: bool,
    bypass_min_gap: bool = False,
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
        running.status = "error"
        running.finished_at = now
        running.error_message = "Kesildi: takılı running kaydı"
        logger.warning(
            "Marked stale running ScanRun #%s for schedule %s",
            running.id,
            sched.id,
        )

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

    if bypass_min_gap:
        return None

    min_gap_sec = min_run_interval_seconds(sched.schedule_type)
    if min_gap_sec > 0 and sched.last_run_at:
        since = now - _as_utc(sched.last_run_at)
        if since < timedelta(seconds=min_gap_sec):
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
        # Kuyruktan gelen tur gecikti; min-gap ile sonraki slotu öldürme.
        threading.Thread(
            target=run_scheduled_scan,
            args=(next_id,),
            kwargs={"bypass_min_gap": True},
            daemon=True,
        ).start()


def run_scheduled_scan(
    scheduled_id: int,
    *,
    force: bool = False,
    bypass_min_gap: bool = False,
) -> None:
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

        skip = _duplicate_skip_reason(
            db,
            sched,
            force=force,
            bypass_min_gap=bypass_min_gap,
        )
        if skip:
            logger.info("Skipping scheduled scan %s (%s)", scheduled_id, skip)
            db.rollback()
            return

        run_row = ScanRun(
            scheduled_scan_id=sched.id,
        started_at=datetime.now(timezone.utc).replace(tzinfo=None),
            status="running",
        )
        db.add(run_row)
        db.commit()
        db.refresh(run_row)

        config = json.loads(sched.config_json)
        payload = execute_scan_config(config, db)
        from app.services.signal_dedupe import apply_repeat_price_filter, scan_fingerprint

        payload = apply_repeat_price_filter(
            db,
            payload,
            user_id=sched.user_id,
            fingerprint=scan_fingerprint(
                user_id=sched.user_id,
                scheduled_scan_id=sched.id,
            ),
        )

        tv_text = payload.get("tradingview_text") or ""
        match_count = int(payload.get("count") or 0)
        skipped_repeat = int(payload.get("skipped_repeat_price") or 0)
        email_sent = False
        notify_errors: list[str] = []

        notify_email = bool(getattr(sched, "notify_email", True))
        send_email = notify_email and (sched.email_to or "").strip()
        email_skipped_repeat = False
        if send_email and match_count == 0 and skipped_repeat > 0:
            send_email = False
            email_skipped_repeat = True
            logger.info(
                "Scheduled scan %s: skipped email (%s same-price repeats, no new hits)",
                scheduled_id,
                skipped_repeat,
            )
        if send_email:
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
        telegram_sent_count = 0
        notify_telegram = bool(getattr(sched, "notify_telegram", True))
        if notify_telegram and (
            telegram_configured()
            or (getattr(sched, "telegram_to", None) or "").strip()
            or (getattr(sched, "telegram_bot_token", None) or "").strip()
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
                    bot_token=getattr(sched, "telegram_bot_token", None),
                )
                telegram_sent_count = int(sent or 0)
                telegram_sent = telegram_sent_count > 0
                if match_count > 0 and not telegram_sent:
                    notify_errors.append(
                        "telegram: eşleşme vardı ama mesaj üretilmedi (token/chat id kaydı veya fiyat)"
                    )
            except Exception as exc:
                notify_errors.append(f"telegram: {exc}")
                logger.exception("Telegram failed for schedule %s", scheduled_id)

        notify_error = " | ".join(notify_errors) if notify_errors else None
        run_row.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
        run_row.status = "success"
        run_row.match_count = match_count
        payload["email_sent"] = email_sent
        payload["email_skipped_repeat"] = email_skipped_repeat
        payload["telegram_sent"] = telegram_sent
        payload["telegram_sent_count"] = telegram_sent_count
        run_row.results_json = json.dumps(payload, ensure_ascii=False)
        run_row.tv_list_text = tv_text
        run_row.email_sent = email_sent
        run_row.error_message = notify_error

        sched.last_run_at = run_row.finished_at
        email_failed = (
            notify_email
            and bool((sched.email_to or "").strip())
            and not email_sent
            and not email_skipped_repeat
        )
        # Boş eşleşmede TG bilerek atlanır; hata sayma.
        telegram_failed = notify_telegram and match_count > 0 and not telegram_sent
        if notify_error and email_failed and telegram_failed:
            sched.last_status = "success_no_email"
        elif notify_error and email_failed:
            sched.last_status = "success_no_email"
        elif notify_error and telegram_failed:
            sched.last_status = "success_no_telegram"
        else:
            sched.last_status = "success"
        sched.last_match_count = match_count
        sched.last_error = notify_error
        db.commit()
        logger.info(
            "Scheduled scan %s done: %s matches, email=%s telegram=%s (%s msg)",
            scheduled_id,
            match_count,
            email_sent,
            telegram_sent,
            telegram_sent_count,
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
            run_row.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
            run_row.status = "error"
            run_row.error_message = str(exc)
            db.commit()
        sched = db.query(ScheduledScan).filter(ScheduledScan.id == scheduled_id).first()
        if sched:
            sched.last_run_at = datetime.now(timezone.utc).replace(tzinfo=None)
            sched.last_status = "error"
            sched.last_error = str(exc)
            db.commit()
    finally:
        db.close()
        _scan_lock.release()
        _run_next_queued()
