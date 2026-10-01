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
from app.utils.datetime_fmt import istanbul_short, utc_iso

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


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _result_items(payload: dict[str, Any], run: ScanRun) -> tuple[list[tuple[str, str]], int]:
    """Return [(symbol, direction), ...] and hit count for one run."""
    results = payload.get("results")
    items: list[tuple[str, str]] = []
    if isinstance(results, list):
        for row in results:
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            items.append((symbol, _direction(row.get("signals"))))
        return items, len(items)
    hits = max(0, _safe_int(run.match_count, _safe_int(payload.get("count"), 0)))
    return items, hits


def _telegram_messages(payload: dict[str, Any], run: ScanRun, hit_count: int) -> int:
    """Actual Telegram messages only (legacy empty-run True flags ignored)."""
    if "telegram_sent_count" in payload:
        return max(0, _safe_int(payload.get("telegram_sent_count"), 0))
    if payload.get("telegram_sent") and hit_count > 0:
        return 1
    return 0


def _email_delivered(payload: dict[str, Any], run: ScanRun) -> bool:
    """True only when an email was actually sent."""
    if run.email_sent is True:
        return True
    if run.email_sent is False:
        return False
    return bool(payload.get("email_sent"))


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
    hit_total = 0
    skipped_repeat = 0
    email_sent = 0
    telegram_sent = 0
    error_runs = 0
    success_runs = 0
    running_runs = 0
    finished_runs = 0
    tf_hits: Counter = Counter()

    scan_rows = []
    for sched in scans:
        meta = _config_meta(sched.config_json)
        sched_runs = by_scan.get(sched.id, [])
        hits = 0
        unique: set[str] = set()
        local_skipped = 0
        finished_sched_runs = 0
        for run in sched_runs:
            status = str(run.status or "").strip().lower()
            if status == "running":
                running_runs += 1
                continue
            finished_runs += 1
            finished_sched_runs += 1
            if status == "error":
                error_runs += 1
            else:
                success_runs += 1

            payload = _parse_payload(run.results_json)
            items, run_hits = _result_items(payload, run)
            hit_total += run_hits
            hits += run_hits
            local_skipped += max(0, _safe_int(payload.get("skipped_repeat_price"), 0))

            if _email_delivered(payload, run):
                email_sent += 1
            tg_msgs = _telegram_messages(payload, run, run_hits)
            telegram_sent += tg_msgs
            tg_ok = tg_msgs > 0
            tg_err = ""
            if run_hits > 0 and not tg_ok:
                tg_err = str(run.error_message or payload.get("telegram_error") or "").strip()

            started = run.started_at
            hour = None
            weekday = None
            last_at = utc_iso(started) if started else None
            if started:
                aware = started if started.tzinfo else started.replace(tzinfo=timezone.utc)
                local_dt = aware.astimezone(zone)
                hour = local_dt.hour
                weekday = local_dt.weekday()

            if items:
                for symbol, direction in items:
                    unique.add(symbol)
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
                            "telegram": "none",
                            "telegram_error": "",
                            "last_at": None,
                        },
                    )
                    rec["count"] += 1
                    rec["scans"].add(sched.name)
                    rec["timeframes"].add(meta["timeframe_label"])
                    rec["directions"][direction] += 1
                    if last_at:
                        rec["last_at"] = last_at
                    if tg_ok:
                        rec["telegram"] = "sent"
                    elif rec["telegram"] != "sent":
                        rec["telegram"] = "missed"
                        if tg_err:
                            rec["telegram_error"] = tg_err[:160]
                    if hour is not None:
                        hour_hits[hour] += 1
                    if weekday is not None:
                        weekday_hits[weekday] += 1
            elif run_hits:
                if hour is not None:
                    hour_hits[hour] += run_hits
                if weekday is not None:
                    weekday_hits[weekday] += run_hits

        last = None
        running_now = None
        for run in reversed(sched_runs):
            st = str(run.status or "").strip().lower()
            if st == "running" and running_now is None:
                running_now = run
                continue
            if st != "running":
                last = run
                break
        if last is None and running_now is None and sched_runs:
            last = sched_runs[-1]

        if last is not None:
            display_status = last.status
            display_at = last.finished_at or last.started_at
        elif running_now is not None:
            display_status = running_now.status
            display_at = running_now.started_at
        else:
            display_status = sched.last_status
            display_at = sched.last_run_at

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
                "runs": finished_sched_runs,
                "hits": hits,
                "unique_symbols": len(unique),
                "skipped_repeat_price": local_skipped,
                "last_status": display_status,
                "last_run_at": utc_iso(display_at),
                "last_run_istanbul": istanbul_short(display_at),
                "is_running": running_now is not None,
                "next_run_at": utc_iso(next_at),
                "next_run_istanbul": istanbul_short(next_at),
            }
        )

    symbols = []
    for rec in symbol_hits.values():
        dirs = rec["directions"]
        direction = "AL" if dirs["AL"] >= dirs["SAT"] else "SAT"
        if dirs["AL"] and dirs["SAT"]:
            direction = "AL/SAT"
        symbols.append(
            {
                "symbol": rec["symbol"],
                "count": rec["count"],
                "scans": sorted(rec["scans"]),
                "timeframes": sorted(rec["timeframes"]),
                "direction": direction,
                "telegram": rec.get("telegram") or "none",
                "telegram_error": rec.get("telegram_error") or "",
                "last_at": rec.get("last_at"),
            }
        )
    symbols.sort(key=lambda row: (-row["count"], row["symbol"]))
    repeats = [row for row in symbols if row["count"] >= 2]

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
            "next_run_istanbul": row.get("next_run_istanbul"),
        }
        for row in scan_rows
        if row["enabled"] and row["next_run_at"]
    ]
    upcoming.sort(key=lambda row: row["next_run_at"] or "")

    unique_total = len(symbol_hits)
    repeat_symbols = len(repeats)
    tg_missed_symbols = sum(1 for row in symbols if row.get("telegram") == "missed")
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
            "runs": finished_runs,
            "runs_today": finished_runs,
            "running_runs": running_runs,
            "success_runs": success_runs,
            "error_runs": error_runs,
            "hits": hit_total,
            "unique_symbols": unique_total,
            "repeat_symbols": repeat_symbols,
            "tg_missed_symbols": tg_missed_symbols,
            "al": al_count,
            "sat": sat_count,
            "skipped_repeat_price": skipped_repeat,
            "email_sent": email_sent,
            "telegram_sent": telegram_sent,
            "peak_hour": peak_label,
            "peak_hour_hits": int(peak_hits),
            "top_timeframe": top_tf,
            "top_timeframe_hits": int(top_tf_hits),
            "symbol_names": [row["symbol"] for row in symbols[:12]],
        },
        "scans": scan_rows,
        "symbols": symbols[:80],
        "repeats": repeats[:40],
        "hours": hours,
        "upcoming": upcoming[:12],
    }
