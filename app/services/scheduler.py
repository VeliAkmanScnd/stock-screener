"""APScheduler integration for scheduled scans."""



from __future__ import annotations



import logging

import threading

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

from app.services.track_runner import run_track_price_update, run_track_weekend_expire



logger = logging.getLogger(__name__)



_scheduler: BackgroundScheduler | None = None

JOB_PREFIX = "scheduled_scan_"

TRACK_PRICE_JOB = "track_price_update"

TRACK_WEEKEND_JOB = "track_weekend_expire"

SCHEDULE_SYNC_JOB = "scheduled_scan_sync"





def _build_trigger(sched: ScheduledScan) -> CronTrigger:

    tz = ZoneInfo(sched.timezone or "Europe/Istanbul")

    minute = int(sched.minute)

    hour = int(sched.hour)

    end_hour = int(sched.end_hour) if sched.end_hour is not None else None

    stype = normalize_schedule_type(sched.schedule_type)

    days = parse_weekdays_field(sched.weekdays)

    day_of_week = weekdays_to_cron(days) if days else None

    if is_window_schedule_type(stype):
        interval = WINDOW_INTERVAL_MINUTES[stype]
        if interval < 60:
            minute_cron = minute_step_cron(interval, minute)
            cron_hour = hour_window_cron(hour, end_hour) if end_hour is not None else "*"
            kwargs: dict = {"hour": cron_hour, "minute": minute_cron, "timezone": tz}
        else:
            step_hours = interval // 60
            if end_hour is not None:
                cron_hour = hour_window_cron(hour, end_hour, step=step_hours)
            else:
                cron_hour = "*" if step_hours == 1 else f"*/{step_hours}"
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





def next_run_for_schedule(sched: ScheduledScan):

    """Return next fire datetime for a schedule (scheduler job or computed trigger)."""

    if not sched.enabled:

        return None



    job_id = f"{JOB_PREFIX}{sched.id}"

    if _scheduler is not None:

        try:

            job = _scheduler.get_job(job_id)

            if job is not None and job.next_run_time is not None:

                return job.next_run_time

        except Exception:

            pass



    try:

        from datetime import datetime, timezone



        return _build_trigger(sched).get_next_fire_time(None, datetime.now(timezone.utc))

    except Exception:

        logger.debug("Could not compute next run for schedule %s", sched.id, exc_info=True)

        return None





def scheduler_status() -> dict[str, object]:

    """Lightweight health info for the UI / debugging."""

    jobs = []

    if _scheduler is not None:

        jobs = [

            {"id": job.id, "next_run": job.next_run_time.isoformat() if job.next_run_time else None}

            for job in _scheduler.get_jobs()

        ]

    return {

        "running": _scheduler is not None,

        "job_count": len(jobs),

        "jobs": jobs[:20],

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

            job_id = f"{JOB_PREFIX}{row.id}"

            existing = None

            try:

                existing = _scheduler.get_job(job_id)

            except Exception:

                existing = None

            desired = _build_trigger(row)

            if existing is None or str(existing.trigger) != str(desired):

                register_job(row)



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

        return

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

    logger.info("Registered schedule job %s (%s)", sched.id, sched.schedule_type)





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

        trigger=CronTrigger(hour="10-23", minute=50, day_of_week="mon-fri", timezone=tz),

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

        sync_jobs_from_db,

        trigger=CronTrigger(minute="*/5", timezone=tz),

        id=SCHEDULE_SYNC_JOB,

        replace_existing=True,

        max_instances=1,

        coalesce=True,

        misfire_grace_time=300,

    )

    logger.info("Track price jobs registered (%s)", tz)


