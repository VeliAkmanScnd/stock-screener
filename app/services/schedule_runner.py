"""Execute scheduled scans and persist results."""

from __future__ import annotations

import heapq
import itertools
import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import ScanRun, ScheduledScan, SessionLocal
from app.services.email_service import send_tv_list_email
from app.services.telegram_service import send_telegram_scan_result, telegram_configured
from app.services.scan_executor import execute_scan_config
from app.services.schedule_helpers import min_run_interval_seconds

logger = logging.getLogger(__name__)

# Same-minute scans run together. Start order is VIOP, then BIST, then Nasdaq,
# but a still-running scan does not hold the next one (a long BIST/Nasdaq must
# not push the following VIOP past its slot). Same schedule still will not
# overlap itself.
_UNIVERSE_PRIORITY = {
    "viop": 0,
    "bist": 1,
    "nasdaq": 2,
    "nasdaq_all": 2,
    "nyse": 3,
    "sp500": 4,
    "all_us": 5,
    "binance": 6,
    "custom": 7,
}
# Cron threads for the same minute start a few hundred ms apart. Wait so the
# whole group is on the heap before the first scan is chosen.
_COALESCE_SEC = 2.0
# Brief gap so VIOP's first requests leave before BIST and Nasdaq start.
_START_GAP_SEC = 0.4

_worker_running = False
_queue_lock = threading.Lock()
_pending_heap: list[tuple[int, int, int]] = []  # (priority, seq, scheduled_id)
_pending_meta: dict[int, dict[str, bool]] = {}  # id -> {force, bypass_min_gap}
_seq = itertools.count()

_RACE_WINDOW = timedelta(minutes=3)
_STALE_RUNNING = timedelta(minutes=45)


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _utc_now() -> datetime:
    try:
        from app.utils.datetime_fmt import effective_utc_now

        return effective_utc_now()
    except Exception:
        return datetime.now(timezone.utc)


def _utc_now_naive() -> datetime:
    return _utc_now().replace(tzinfo=None)


def _priority_base(universe: str, name: str) -> int:
    """1 VIOP, 2 BIST, 3 Nasdaq. Lower return value runs first."""
    if universe == "viop" or "viop" in name:
        return 0
    if universe == "bist" or name.startswith("bist") or " bist" in f" {name}":
        return 1
    if universe.startswith("nasdaq") or "nasdaq" in name or name.startswith("nas"):
        return 2
    return _UNIVERSE_PRIORITY.get(universe, 40)


def _schedule_priority(sched: ScheduledScan | None, scheduled_id: int = 0) -> int:
    """VIOP, then BIST, then Nasdaq. Same market stays in id order."""
    if sched is None:
        return 50 + max(0, scheduled_id)
    try:
        cfg = json.loads(sched.config_json or "{}")
    except json.JSONDecodeError:
        cfg = {}
    universe = str(cfg.get("custom_source_universe") or cfg.get("universe") or "").strip().lower()
    name = (sched.name or "").strip().lower()
    return _priority_base(universe, name) * 1000 + int(sched.id)


def cleanup_stale_running_scans(
    max_age: timedelta | None = None,
    *,
    protect_schedule_ids: set[int] | None = None,
) -> int:
    """Mark orphan 'running' rows as error so schedules are not blocked after restart.

    Also clears rows whose started_at is in the future (clock-skew leftovers) —
    those would otherwise look 'young' forever and block the schedule.
    """
    # max_age=0 → clear every running row not in protect set (use on process start).
    age_limit = max_age if max_age is not None else timedelta(minutes=10)
    protected = protect_schedule_ids or set()
    db = SessionLocal()
    try:
        now = _utc_now()
        now_naive = now.replace(tzinfo=None)
        rows = (
            db.query(ScanRun)
            .filter(ScanRun.status == "running")
            .order_by(ScanRun.started_at.asc())
            .all()
        )
        fixed = 0
        for row in rows:
            sid = int(row.scheduled_scan_id) if row.scheduled_scan_id is not None else None
            if sid is not None and sid in protected:
                continue
            started = _as_utc(row.started_at) if row.started_at else None
            if started is not None:
                age = now - started
                # Keep only truly recent, non-future rows within grace.
                if age_limit > timedelta(0) and timedelta(0) <= age < age_limit:
                    continue
            row.status = "error"
            row.finished_at = now_naive
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
                sched.last_run_at = now_naive
            try:
                from app.services.scan_jobs import clear_schedule_progress

                if sid is not None:
                    clear_schedule_progress(sid)
            except Exception:
                pass
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

    now = _utc_now()
    now_naive = now.replace(tzinfo=None)
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
        # Future started_at (clock skew) or older than grace → cut and continue.
        if age < timedelta(0) or age >= _STALE_RUNNING:
            running.status = "error"
            running.finished_at = now_naive
            running.error_message = "Kesildi: takılı running kaydı"
            logger.warning(
                "Marked stale running ScanRun #%s for schedule %s",
                running.id,
                sched.id,
            )
        else:
            return f"already running (run #{running.id})"
    elif running:
        running.status = "error"
        running.finished_at = now_naive
        running.error_message = "Kesildi: takılı running kaydı"

    recent = (
        db.query(ScanRun)
        .filter(
            ScanRun.scheduled_scan_id == sched.id,
            ScanRun.started_at >= now_naive - _RACE_WINDOW,
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


def _enqueue_scheduled_scan(
    scheduled_id: int,
    *,
    force: bool = False,
    bypass_min_gap: bool = False,
) -> None:
    db = SessionLocal()
    try:
        sched = db.query(ScheduledScan).filter(ScheduledScan.id == scheduled_id).first()
        priority = _schedule_priority(sched, scheduled_id)
        name = (sched.name if sched else "") or f"#{scheduled_id}"
    finally:
        db.close()

    with _queue_lock:
        meta = _pending_meta.get(scheduled_id)
        if meta is not None:
            # Already queued: keep highest urgency flags.
            meta["force"] = bool(meta.get("force") or force)
            meta["bypass_min_gap"] = bool(meta.get("bypass_min_gap") or bypass_min_gap)
            logger.info("Scheduled scan %s already queued — flags refreshed", scheduled_id)
            return
        _pending_meta[scheduled_id] = {
            "force": bool(force),
            "bypass_min_gap": bool(bypass_min_gap),
        }
        heapq.heappush(_pending_heap, (priority, next(_seq), scheduled_id))
    try:
        from app.services.scan_jobs import begin_schedule_progress

        begin_schedule_progress(scheduled_id, name=name, queued=True)
    except Exception:
        pass
    logger.info(
        "Scheduled scan %s queued (priority=%s, force=%s)",
        scheduled_id,
        priority,
        force,
    )


def _dequeue_next() -> tuple[int, bool, bool] | None:
    with _queue_lock:
        while _pending_heap:
            _priority, _seq_n, scheduled_id = heapq.heappop(_pending_heap)
            meta = _pending_meta.pop(scheduled_id, None)
            if meta is None:
                continue
            return (
                scheduled_id,
                bool(meta.get("force")),
                bool(meta.get("bypass_min_gap")),
            )
        return None


def _kick_worker() -> None:
    global _worker_running
    with _queue_lock:
        if _worker_running:
            return
        if not _pending_heap:
            return
        _worker_running = True
    threading.Thread(target=_worker_loop, daemon=True, name="scheduled-scan-worker").start()


def _worker_loop() -> None:
    global _worker_running
    try:
        while True:
            # Collect every scan that fired on this minute, then start them in
            # priority order without waiting for one to finish.
            time.sleep(_COALESCE_SEC)
            batch: list[tuple[int, bool, bool]] = []
            while True:
                item = _dequeue_next()
                if item is None:
                    break
                batch.append(item)
            for index, (scheduled_id, force, bypass_min_gap) in enumerate(batch):
                if index:
                    time.sleep(_START_GAP_SEC)
                threading.Thread(
                    target=_execute_scheduled_scan,
                    args=(scheduled_id,),
                    kwargs={
                        "force": force,
                        "bypass_min_gap": bypass_min_gap,
                    },
                    daemon=True,
                    name=f"scheduled-scan-run-{scheduled_id}",
                ).start()
            with _queue_lock:
                if _pending_heap:
                    continue
                _worker_running = False
                return
    except Exception:
        logger.exception("Scheduled scan worker failed")
        with _queue_lock:
            _worker_running = False


def run_scheduled_scan(
    scheduled_id: int,
    *,
    force: bool = False,
    bypass_min_gap: bool = False,
) -> None:
    """Queue a scheduled scan. Same-minute jobs start together: VIOP, then BIST, then Nasdaq."""
    _enqueue_scheduled_scan(
        scheduled_id,
        force=force,
        bypass_min_gap=bypass_min_gap,
    )
    _kick_worker()


def _execute_scheduled_scan(
    scheduled_id: int,
    *,
    force: bool = False,
    bypass_min_gap: bool = False,
) -> None:
    """Run one scheduled scan. Other schedules may run at the same time."""
    db = SessionLocal()
    run_row: ScanRun | None = None
    try:
        db.execute(text("BEGIN IMMEDIATE"))
        sched = db.query(ScheduledScan).filter(ScheduledScan.id == scheduled_id).first()
        if not sched or (not sched.enabled and not force):
            db.rollback()
            try:
                from app.services.scan_jobs import clear_schedule_progress

                clear_schedule_progress(scheduled_id)
            except Exception:
                pass
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
            try:
                from app.services.scan_jobs import clear_schedule_progress

                clear_schedule_progress(scheduled_id)
            except Exception:
                pass
            return

        # Register live progress before the DB 'running' row so Özet never shows
        # a ghost "sürüyor" without percent/phase after refresh.
        from app.services.scan_jobs import (
            begin_schedule_progress,
            finish_schedule_progress,
            make_schedule_progress_callback,
            update_schedule_progress,
        )

        begin_schedule_progress(
            scheduled_id,
            name=sched.name or f"#{scheduled_id}",
            queued=False,
        )

        run_row = ScanRun(
            scheduled_scan_id=sched.id,
            started_at=_utc_now_naive(),
            status="running",
        )
        db.add(run_row)
        db.commit()
        db.refresh(run_row)
        update_schedule_progress(scheduled_id, run_id=run_row.id, status="running")
        progress = make_schedule_progress_callback(scheduled_id)

        config = json.loads(sched.config_json)
        payload = execute_scan_config(config, db, progress_callback=progress)
        from app.services.signal_dedupe import apply_repeat_price_filter, scan_fingerprint

        update_schedule_progress(
            scheduled_id,
            progress=92,
            phase="dedupe",
            message="Tekrarlar eleniyor…",
        )
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

        update_schedule_progress(
            scheduled_id,
            progress=95,
            phase="notify",
            message="Bildirimler gönderiliyor…",
        )

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
                from app.services.notify_format import format_match_lines_for_email

                match_lines = format_match_lines_for_email(
                    list(payload.get("results") or []),
                    timeframe=str(payload.get("timeframe") or ""),
                )
                body = (
                    f"Zamanlanmış tarama tamamlandı.\n\n"
                    f"Ad: {sched.name}\n"
                    f"Evren: {payload.get('universe')}\n"
                    f"Zaman dilimi: {payload.get('timeframe')}\n"
                    f"Eşleşme: {match_count}\n"
                )
                if match_lines:
                    body += "\nSinyaller:\n" + match_lines + "\n"
                body += "\nTradingView sembol listesi ekte (.txt).\n"
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
        run_row.finished_at = _utc_now_naive()
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
        finish_schedule_progress(
            scheduled_id,
            ok=True,
            message=f"Tamamlandı — {match_count} eşleşme",
        )
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
        try:
            from app.services.scan_jobs import finish_schedule_progress

            finish_schedule_progress(scheduled_id, ok=False, message=str(exc)[:160])
        except Exception:
            pass
        if run_row:
            run_row.finished_at = _utc_now_naive()
            run_row.status = "error"
            run_row.error_message = str(exc)
            db.commit()
        sched = db.query(ScheduledScan).filter(ScheduledScan.id == scheduled_id).first()
        if sched:
            sched.last_run_at = _utc_now_naive()
            sched.last_status = "error"
            sched.last_error = str(exc)
            db.commit()
    finally:
        db.close()
