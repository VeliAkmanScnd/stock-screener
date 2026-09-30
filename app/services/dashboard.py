"""Scheduled-scan dashboard stats (Europe/Istanbul calendar periods)."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.config import DEFAULT_SCHEDULE_TIMEZONE
from app.database import ScanRun, ScheduledScan, User
from app.services.scheduler import next_run_for_schedule
from app.services.runtime_status import build_runtime_status
from app.services.track_levels import TIMEFRAME_LEVEL_BENCHMARKS
from app.utils.datetime_fmt import utc_iso

Period = Literal["day", "week", "all"]

UNIVERSE_LABELS = {
    "bist": "BIST",
    "viop": "VIOP",
    "nasdaq": "NASDAQ",
    "nyse": "NYSE",
    "sp500": "S&P 500",
    "all_us": "NASDAQ + NYSE + S&P 500",
    "binance": "Binance",
    "custom": "Özel",
}

WEEKDAY_TR = ("Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz")


def _tz() -> ZoneInfo:
    try:
        return ZoneInfo(DEFAULT_SCHEDULE_TIMEZONE or "Europe/Istanbul")
    except Exception:
        return ZoneInfo("Europe/Istanbul")


def _period_bounds(
    period: Period,
    now: datetime | None = None,
) -> tuple[datetime | None, datetime, str, str]:
    """Return (start_local|None, end_local, label, period)."""
    zone = _tz()
    local = (now or datetime.now(timezone.utc)).astimezone(zone)
    end_local = local
    if period == "all":
        return None, end_local, "Tüm zamanlar", "all"
    if period == "week":
        start_local = datetime.combine(local.date(), time.min, tzinfo=zone) - timedelta(
            days=local.weekday()
        )
        end_week = start_local + timedelta(days=7)
        label = f"{start_local.strftime('%Y-%m-%d')} → {min(end_local, end_week).strftime('%Y-%m-%d')}"
        return start_local, end_local, label, "week"
    start_local = datetime.combine(local.date(), time.min, tzinfo=zone)
    return start_local, end_local, local.strftime("%Y-%m-%d"), "day"


def _naive_utc(dt: datetime) -> datetime:
    aware = dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return aware.replace(tzinfo=None)


def _tf_label(timeframe: str | None) -> str:
    key = (timeframe or "").strip()
    row = TIMEFRAME_LEVEL_BENCHMARKS.get(key)
    if row:
        return str(row["label"])
    return key or "—"


def _universe_label(universe: str | None) -> str:
    key = (universe or "").strip().lower()
    return UNIVERSE_LABELS.get(key, (universe or "—").upper())


def _direction(signals: Any) -> str:
    if not isinstance(signals, dict):
        return "AL"
    buy = bool(signals.get("bias_ts_buy") or signals.get("buy"))
    sell = bool(signals.get("bias_ts_sell") or signals.get("sell"))
    if buy and sell:
        side = str(signals.get("bias_ts_side") or signals.get("side") or "buy").strip().lower()
        return "SAT" if side == "sell" else "AL"
    if sell and not buy:
        return "SAT"
    return "AL"


def _config_meta(config_json: str | None) -> dict[str, str]:
    try:
        cfg = json.loads(config_json or "{}")
    except json.JSONDecodeError:
        cfg = {}
    universe = str(cfg.get("universe") or "")
    source = str(cfg.get("custom_source_universe") or "")
    timeframe = str(cfg.get("timeframe") or "")
    return {
        "universe": universe,
        "universe_label": _universe_label(source or universe),
        "timeframe": timeframe,
        "timeframe_label": _tf_label(timeframe),
    }


def _parse_payload(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _normalize_period(period: str | None) -> Period:
    key = (period or "day").strip().lower()
    if key in ("week", "hafta", "w"):
        return "week"
    if key in ("all", "tum", "tüm", "total", "a"):
        return "all"
    return "day"


def build_today_dashboard(db: Session, user: User, period: str | None = "day") -> dict[str, Any]:
    period_key = _normalize_period(period)
    start_local, _end_local, range_label, period_key = _period_bounds(period_key)
    start_utc = _naive_utc(start_local) if start_local else None
    run_limit = 8000 if period_key == "all" else (4000 if period_key == "week" else 2500)

    q = db.query(ScheduledScan)
    if user.role != "admin":
        q = q.filter(ScheduledScan.user_id == user.id)
    scans = q.order_by(ScheduledScan.name.asc()).all()
    scan_ids = [s.id for s in scans]
    owners: dict[int, str] = {}
    if scan_ids:
        owner_ids = {s.user_id for s in scans}
        owners = {
            u.id: u.username
            for u in db.query(User).filter(User.id.in_(owner_ids)).all()
        }

    runs: list[ScanRun] = []
    if scan_ids:
        rq = db.query(ScanRun).filter(ScanRun.scheduled_scan_id.in_(scan_ids))
        if start_utc is not None:
            rq = rq.filter(ScanRun.started_at >= start_utc)
        runs = rq.order_by(ScanRun.started_at.asc()).limit(run_limit).all()

    zone = _tz()
    by_scan: dict[int, list[ScanRun]] = defaultdict(list)
    for run in runs:
        by_scan[run.scheduled_scan_id].append(run)

    symbol_hits: dict[str, dict[str, Any]] = {}
    hour_hits = Counter()
    weekday_hits = Counter()
    al_count = 0
    sat_count = 0
    skipped_repeat = 0
    email_sent = 0
    telegram_sent = 0
    error_runs = 0
    success_runs = 0
    tf_hits: Counter = Counter()

    scan_rows = []
    for sched in scans:
        meta = _config_meta(sched.config_json)
        sched_runs = by_scan.get(sched.id, [])
        hits = 0
        unique: set[str] = set()
        local_skipped = 0
        last = sched_runs[-1] if sched_runs else None
        for run in sched_runs:
            if run.status == "error":
                error_runs += 1
            elif run.status and str(run.status).startswith("success"):
                success_runs += 1
            payload = _parse_payload(run.results_json)
            if run.email_sent or payload.get("email_sent"):
                email_sent += 1
            if payload.get("telegram_sent"):
                telegram_sent += 1
            local_skipped += int(payload.get("skipped_repeat_price") or 0)
            results = payload.get("results") if payload else None
            started = run.started_at
            hour = None
            weekday = None
            if started:
                aware = started if started.tzinfo else started.replace(tzinfo=timezone.utc)
                local_dt = aware.astimezone(zone)
                hour = local_dt.hour
                weekday = local_dt.weekday()
            if isinstance(results, list):
                hits += len(results)
                for item in results:
                    symbol = str(item.get("symbol") or "").strip().upper()
                    if not symbol:
                        continue
                    unique.add(symbol)
                    direction = _direction(item.get("signals"))
                    if direction == "SAT":
                        sat_count += 1
                    else:
                        al_count += 1
                    rec = symbol_hits.setdefault(
                        symbol,
                        {
                            "symbol": symbol,
                            "count": 0,
                            "scans": set(),
                            "timeframes": set(),
                            "directions": Counter(),
                        },
                    )
                    rec["count"] += 1
                    rec["scans"].add(sched.name)
                    rec["timeframes"].add(meta["timeframe_label"])
                    rec["directions"][direction] += 1
                    if hour is not None:
                        hour_hits[hour] += 1
                    if weekday is not None:
                        weekday_hits[weekday] += 1
            else:
                n = int(run.match_count or 0)
                hits += n
                if hour is not None:
                    hour_hits[hour] += n
                if weekday is not None:
                    weekday_hits[weekday] += n

        skipped_repeat += local_skipped
        if hits:
            tf_hits[meta["timeframe_label"]] += hits
        next_at = next_run_for_schedule(sched) if sched.enabled else None
        scan_rows.append(
            {
                "id": sched.id,
                "name": sched.name,
                "owner": owners.get(sched.user_id) or "",
                "enabled": bool(sched.enabled),
                "universe": meta["universe"],
                "universe_label": meta["universe_label"],
                "timeframe": meta["timeframe"],
                "timeframe_label": meta["timeframe_label"],
                "runs": len(sched_runs),
                "hits": hits,
                "unique_symbols": len(unique),
                "skipped_repeat_price": local_skipped,
                "last_status": last.status if last else sched.last_status,
                "last_run_at": utc_iso(last.finished_at or last.started_at)
                if last
                else utc_iso(sched.last_run_at),
                "next_run_at": utc_iso(next_at),
            }
        )

    repeats = []
    for rec in symbol_hits.values():
        dirs = rec["directions"]
        direction = "AL" if dirs["AL"] >= dirs["SAT"] else "SAT"
        if dirs["AL"] and dirs["SAT"]:
            direction = "AL/SAT"
        repeats.append(
            {
                "symbol": rec["symbol"],
                "count": rec["count"],
                "scans": sorted(rec["scans"]),
                "timeframes": sorted(rec["timeframes"]),
                "direction": direction,
            }
        )
    repeats.sort(key=lambda row: (-row["count"], row["symbol"]))

    if period_key == "week":
        chart_mode = "weekday"
        hours = [
            {"hour": i, "label": WEEKDAY_TR[i], "hits": int(weekday_hits.get(i, 0))}
            for i in range(7)
        ]
    else:
        chart_mode = "hour"
        hours = [
            {"hour": h, "label": f"{h}", "hits": int(hour_hits.get(h, 0))}
            for h in range(8, 24)
        ]

    upcoming = [
        {
            "id": row["id"],
            "name": row["name"],
            "timeframe_label": row["timeframe_label"],
            "universe_label": row["universe_label"],
            "next_run_at": row["next_run_at"],
        }
        for row in scan_rows
        if row["enabled"] and row["next_run_at"]
    ]
    upcoming.sort(key=lambda row: row["next_run_at"] or "")

    unique_total = len(symbol_hits)
    repeat_symbols = sum(1 for row in repeats if row["count"] >= 2)
    hit_total = al_count + sat_count
    if period_key == "week" and weekday_hits:
        peak_key, peak_hits = weekday_hits.most_common(1)[0]
        peak_label = WEEKDAY_TR[peak_key]
    elif hour_hits:
        peak_key, peak_hits = hour_hits.most_common(1)[0]
        peak_label = f"{peak_key}:00"
    else:
        peak_label, peak_hits = None, 0
    top_tf, top_tf_hits = (tf_hits.most_common(1)[0] if tf_hits else ("—", 0))

    period_titles = {
        "day": "Günün özeti",
        "week": "Haftanın özeti",
        "all": "Tüm zamanlar",
    }

    return {
        "period": period_key,
        "period_label": period_titles[period_key],
        "date": range_label,
        "timezone": DEFAULT_SCHEDULE_TIMEZONE or "Europe/Istanbul",
        "service": build_runtime_status(),
        "chart_mode": chart_mode,
        "kpis": {
            "enabled_scans": sum(1 for s in scans if s.enabled),
            "runs": len(runs),
            "runs_today": len(runs),
            "success_runs": success_runs,
            "error_runs": error_runs,
            "hits": hit_total,
            "unique_symbols": unique_total,
            "repeat_symbols": repeat_symbols,
            "al": al_count,
            "sat": sat_count,
            "skipped_repeat_price": skipped_repeat,
            "email_sent": email_sent,
            "telegram_sent": telegram_sent,
            "peak_hour": peak_label,
            "peak_hour_hits": int(peak_hits),
            "top_timeframe": top_tf,
            "top_timeframe_hits": int(top_tf_hits),
        },
        "scans": scan_rows,
        "repeats": repeats[:40],
        "hours": hours,
        "upcoming": upcoming[:12],
    }
