"""APScheduler integration for scheduled scans."""
from __future__ import annotations
import logging
import threading
from datetime import timedelta
from zoneinfo import ZoneInfo
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from app.config import TRACK_PRICE_CHECK_TIMEZONE
from app.database import ScheduledScan, SessionLocal
from app.services.schedule_helpers import (
    WINDOW_INTERVAL_MINUTES,
    hour_window_cron,
    is_window_schedule_type,
    minute_step_cron,
    normalize_schedule_type,
    parse_weekdays_field,
    weekdays_to_cron,
)
from app.services.scheduler_lock import acquire_scheduler_lock, release_scheduler_lock
from app.services.schedule_runner import run_scheduled_scan
from app.services.track_runner import (
    run_track_archive,
    run_track_price_update,
    run_track_weekend_expire,
)
logger = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None
JOB_PREFIX = "scheduled_scan_"
TRACK_PRICE_JOB = "track_price_update"
TRACK_WEEKEND_JOB = "track_weekend_expire"
TRACK_ARCHIVE_JOB = "track_archive_expired"
SCHEDULE_SYNC_JOB = "scheduled_scan_sync"
NASDAQ_LIQUID_JOB = "nasdaq_liquid_refresh"
VIOP_CONTRACTS_JOB = "viop_contracts_refresh"


def _refresh_nasdaq_liquid_job() -> None:
    try:
        from app.services.data_fetcher import refresh_nasdaq_liquid_universe

        result = refresh_nasdaq_liquid_universe(force=True)
        logger.info("NASDAQ liquid refresh: %s", result)
    except Exception:
        logger.exception("NASDAQ liquid daily refresh failed")


def _refresh_viop_contracts_job() -> None:
    try:
        from app.services.viop_contracts import refresh_viop_contracts

        result = refresh_viop_contracts(force=True)
        logger.info("VIOP contracts refresh: %s", result)
    except Exception:
        logger.exception("VIOP contracts daily refresh failed")

def _build_trigger(sched: ScheduledScan) -> CronTrigger:
    tz_name = (sched.timezone or "Europe/Istanbul").strip() or "Europe/Istanbul"
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("Europe/Istanbul")
    minute = int(sched.minute or 0)
    hour = int(sched.hour or 0)
    end_hour = int(sched.end_hour) if sched.end_hour is not None else None
    stype = normalize_schedule_type(sched.schedule_type)
    days = parse_weekdays_field(sched.weekdays)
    day_of_week = weekdays_to_cron(days) if days else None
    if is_window_schedule_type(stype):
        # Bitiş boşsa seans sonu varsay (eski kayıtlarda NULL kalabiliyordu).
        if end_hour is None:
            end_hour = 18
        interval = WINDOW_INTERVAL_MINUTES[stype]
        if interval < 60:
            minute_cron = minute_step_cron(interval, minute)
            cron_hour = hour_window_cron(hour, end_hour)
            kwargs: dict = {"hour": cron_hour, "minute": minute_cron, "timezone": tz}
        else:
            step_hours = max(1, interval // 60)
            cron_hour = hour_window_cron(hour, end_hour, step=step_hours)
            kwargs = {"hour": cron_hour, "minute": minute, "timezone": tz}
        if day_of_week:
            kwargs["day_of_week"] = day_of_week
        return CronTrigger(**kwargs)
    if stype == "1wk" and not days:
        dow = int(sched.weekday if sched.weekday is not None else 0)
        return CronTrigger(day_of_week=dow, hour=hour, minute=minute, timezone=tz)
    if days:
        return CronTrigger(
            day_of_week=weekdays_to_cron(days),
            hour=hour,
            minute=minute,
            timezone=tz,
        )
    return CronTrigger(hour=hour, minute=minute, timezone=tz)


def schedule_window_snapshot(sched: ScheduledScan) -> dict:
    """Explain whether 'now' is inside the schedule window (Istanbul/local TZ)."""
    from app.utils.datetime_fmt import effective_utc_now

    tz_name = (sched.timezone or "Europe/Istanbul").strip() or "Europe/Istanbul"
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("Europe/Istanbul")
    now_local = effective_utc_now().astimezone(tz)
    stype = normalize_schedule_type(sched.schedule_type)
    days = parse_weekdays_field(sched.weekdays)
    hour = int(sched.hour or 0)
    minute = int(sched.minute or 0)
    end_hour = int(sched.end_hour) if sched.end_hour is not None else (
        18 if is_window_schedule_type(stype) else hour
    )
    weekday_ok = (not days) or (now_local.weekday() in days)
    if is_window_schedule_type(stype):
        interval = WINDOW_INTERVAL_MINUTES.get(stype, 15)
        if interval < 60:
            phase = minute % interval
            last_slot_min = max(range(phase, 60, interval), default=phase)
            before_start = now_local.hour < hour or (
                now_local.hour == hour and now_local.minute < phase
            )
        else:
            last_slot_min = minute
            before_start = now_local.hour < hour or (
                now_local.hour == hour and now_local.minute < minute
            )
        past_end = now_local.hour > end_hour or (
            now_local.hour == end_hour and now_local.minute > last_slot_min
        )
        hour_ok = (not before_start) and (not past_end)
        window_label = f"{hour:02d}:{minute:02d}–{end_hour:02d}:{last_slot_min:02d}"
    else:
        hour_ok = True
        window_label = f"{hour:02d}:{minute:02d}"
        past_end = False
        before_start = False
    inside = bool(sched.enabled and weekday_ok and hour_ok)
    reason = ""
    if not sched.enabled:
        reason = "durduruldu"
    elif not weekday_ok:
        reason = "bugün seçili günlerde yok"
    elif is_window_schedule_type(stype) and before_start:
        reason = f"pencere henüz açılmadı ({window_label})"
    elif is_window_schedule_type(stype) and past_end:
        reason = f"bugünkü pencere bitti ({window_label})"
    return {
        "timezone": str(tz),
        "now_local": now_local.isoformat(),
        "window_label": window_label,
        "inside_window": inside,
        "reason": reason,
        "weekdays": days,
        "hour": hour,
        "end_hour": end_hour if is_window_schedule_type(stype) else None,
    }


def _misfire_grace_seconds(schedule_type: str | None) -> int:
    """Allow catch-up window based on cadence."""
    stype = normalize_schedule_type(schedule_type)
    if stype in WINDOW_INTERVAL_MINUTES:
        return WINDOW_INTERVAL_MINUTES[stype] * 60
    if stype == "1wk":
        return 7 * 24 * 3600
    return 24 * 3600


def _trigger_scheduled_scan(scheduled_id: int) -> None:
    # Never run heavy scan work on the APScheduler thread — a long all_us job
    # would block later triggers (max_instances=1) and stall other schedules.
    threading.Thread(
        target=run_scheduled_scan,
        args=(scheduled_id,),
        kwargs={"force": False},
        daemon=True,
        name=f"scheduled-scan-{scheduled_id}",
    ).start()


def _as_utc_ts(dt):
    from datetime import timezone as tz

    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz.utc)
    return dt.astimezone(tz.utc)


def next_run_for_schedule(sched: ScheduledScan):
    """Return next fire datetime in absolute time (computed from cron, not stale job TZ)."""
    if not sched.enabled:
        return None
    from app.utils.datetime_fmt import effective_utc_now

    now_utc = effective_utc_now()
    try:
        computed = _build_trigger(sched).get_next_fire_time(None, now_utc)
    except Exception:
        logger.debug("Could not compute next run for schedule %s", sched.id, exc_info=True)
        computed = None

    # Keep APScheduler job in sync, but always trust freshly computed fire time
    # (scheduler/job TZ mismatches were shifting 'Sonraki' by hours).
    if _scheduler is not None and computed is not None:
        try:
            job_id = f"{JOB_PREFIX}{sched.id}"
            job = _scheduler.get_job(job_id)
            job_next = job.next_run_time if job is not None else None
            if job is None or job_next is None:
                register_job(sched)
            elif abs((_as_utc_ts(job_next) - _as_utc_ts(computed)).total_seconds()) > 90:
                logger.warning(
                    "Schedule %s job next=%s drift vs computed=%s — re-registering",
                    sched.id,
                    job_next,
                    computed,
                )
                register_job(sched)
        except Exception:
            logger.debug("Job heal failed for %s", sched.id, exc_info=True)

    return computed

def scheduler_status() -> dict[str, object]:
    """Lightweight health info for the UI / debugging."""
    from app.utils.datetime_fmt import utc_iso

    jobs = []
    if _scheduler is not None:
        for job in _scheduler.get_jobs():
            jobs.append(
                {
                    "id": job.id,
                    "next_run": utc_iso(job.next_run_time) if job.next_run_time else None,
                }
            )
    return {
        "running": _scheduler is not None,
        "job_count": len(jobs),
        "jobs": jobs[:20],
        "timezone": "UTC",
    }


def sync_jobs_from_db() -> None:
    """Reconcile APScheduler jobs with enabled DB schedules (no needless re-register)."""
    if _scheduler is None:
        return
    db = SessionLocal()
    try:
        rows = db.query(ScheduledScan).filter(ScheduledScan.enabled.is_(True)).all()
        enabled_ids = {row.id for row in rows}
        existing_scan_jobs = {
            job.id for job in _scheduler.get_jobs() if job.id.startswith(JOB_PREFIX)
        }
        for row in rows:
            try:
                job_id = f"{JOB_PREFIX}{row.id}"
                existing = None
                try:
                    existing = _scheduler.get_job(job_id)
                except Exception:
                    existing = None
                desired = _build_trigger(row)
                if existing is None or str(existing.trigger) != str(desired):
                    register_job(row)
                else:
                    nxt = existing.next_run_time
                    logger.debug(
                        "Schedule %s ok trigger=%s next=%s",
                        row.id,
                        desired,
                        nxt,
                    )
            except Exception:
                logger.exception("Failed to sync schedule job %s (%s)", row.id, row.name)
        stale_jobs = existing_scan_jobs - {f"{JOB_PREFIX}{sid}" for sid in enabled_ids}
        for job_id in stale_jobs:
            try:
                _scheduler.remove_job(job_id)
            except Exception:
                pass
    finally:
        db.close()


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    if not acquire_scheduler_lock():
        logger.warning("Scheduler lock not acquired — timed scans will not run in this process")
        return
    try:
        from app.services.schedule_runner import cleanup_stale_running_scans

        # After restart nothing is truly running — clear all orphan rows
        # (including future started_at left by clock skew).
        cleanup_stale_running_scans(max_age=timedelta(0))
    except Exception:
        logger.exception("Stale running scan cleanup failed")
    # CronTrigger carries Europe/Istanbul; scheduler clock stays UTC.
    # Wrong Windows *display* TZ is fine if automatic time (correct UTC) is on.
    from app.utils.datetime_fmt import clock_skew_info

    skew = clock_skew_info()
    if skew.get("windows_tz_mismatch"):
        logger.info(
            "Windows local face ≠ Istanbul (drift=%ss, mode=%s). "
            "Schedules use UTC→Europe/Istanbul; keep automatic time ON.",
            skew.get("drift_seconds"),
            skew.get("mode"),
        )

    _scheduler = BackgroundScheduler(
        timezone="UTC",
        executors={"default": ThreadPoolExecutor(max_workers=4)},
        job_defaults={
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": 3600,
        },
    )
    _scheduler.start()
    reload_all_jobs()
    register_track_jobs()
    # Warm NASDAQ liquid list in background (first build can take several minutes).
    threading.Thread(
        target=_refresh_nasdaq_liquid_job,
        daemon=True,
        name="nasdaq-liquid-warmup",
    ).start()
    threading.Thread(
        target=_refresh_viop_contracts_job,
        daemon=True,
        name="viop-contracts-warmup",
    ).start()
    logger.info("Scan scheduler started")

def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Scan scheduler stopped")
    release_scheduler_lock()

def reload_all_jobs() -> None:
    if _scheduler is None:
        return
    for job in list(_scheduler.get_jobs()):
        if job.id.startswith(JOB_PREFIX):
            try:
                _scheduler.remove_job(job.id)
            except Exception:
                pass
    sync_jobs_from_db()

def register_job(sched: ScheduledScan) -> None:
    if _scheduler is None:
        return
    job_id = f"{JOB_PREFIX}{sched.id}"
    if not sched.enabled:
        try:
            _scheduler.remove_job(job_id)
        except Exception:
            pass
        return
    trigger = _build_trigger(sched)
    _scheduler.add_job(
        _trigger_scheduled_scan,
        trigger=trigger,
        id=job_id,
        args=[sched.id],
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=_misfire_grace_seconds(sched.schedule_type),
    )
    from datetime import datetime, timezone

    from app.utils.datetime_fmt import effective_utc_now

    nxt = trigger.get_next_fire_time(None, effective_utc_now())
    logger.info(
        "Registered schedule job %s (%s) trigger=%s next=%s",
        sched.id,
        sched.schedule_type,
        trigger,
        nxt,
    )

def unregister_job(scheduled_id: int) -> None:
    if _scheduler is None:
        return
    job_id = f"{JOB_PREFIX}{scheduled_id}"
    try:
        _scheduler.remove_job(job_id)
    except Exception:
        pass

def register_track_jobs() -> None:
    if _scheduler is None:
        return
    tz = ZoneInfo(TRACK_PRICE_CHECK_TIMEZONE or "Europe/Istanbul")
    _scheduler.add_job(
        run_track_price_update,
        trigger=CronTrigger(hour="10-23", minute=0, day_of_week="mon-fri", timezone=tz),
        id=TRACK_PRICE_JOB,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    _scheduler.add_job(
        run_track_weekend_expire,
        trigger=CronTrigger(day_of_week="fri", hour=23, minute=5, timezone=tz),
        id=TRACK_WEEKEND_JOB,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    _scheduler.add_job(
        run_track_archive,
        trigger=CronTrigger(hour=0, minute=10, timezone=tz),
        id=TRACK_ARCHIVE_JOB,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    _scheduler.add_job(
        sync_jobs_from_db,
        trigger=CronTrigger(minute="*/5", timezone=tz),
        id=SCHEDULE_SYNC_JOB,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )
    # US seansı öncesi: NASDAQ en hacimli 1000 listesini yenile (İstanbul 08:00).
    _scheduler.add_job(
        _refresh_nasdaq_liquid_job,
        trigger=CronTrigger(hour=8, minute=0, timezone=tz),
        id=NASDAQ_LIQUID_JOB,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    # VIOP kapanış sonrası: hesaplayıcı fiyat + teminat oranı + kaldıraç (İstanbul 18:45).
    _scheduler.add_job(
        _refresh_viop_contracts_job,
        trigger=CronTrigger(
            hour=18, minute=45, day_of_week="mon-fri", timezone=tz
        ),
        id=VIOP_CONTRACTS_JOB,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    logger.info("Track price jobs registered (%s)", tz)
