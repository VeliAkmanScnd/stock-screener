"""Ranked performance reports for tracked scan results."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.database import TrackPosition
from app.services.track_levels import MIN_SAMPLE_FOR_RANK, level_benchmarks_for_api, realized_r
from app.services.track_service import (
    WATCH_STATUSES,
    _hours_between,
    excursion_pcts,
    position_to_dict,
)

TIMEFRAME_LABELS = {
    "5m": "5 dakika",
    "15m": "15 dakika",
    "30m": "30 dakika",
    "1h": "1 saat",
    "2h": "2 saat",
    "4h": "4 saat",
    "8h": "8 saat",
    "12h": "12 saat",
    "1d": "1 gün",
    "1wk": "1 hafta",
}

GROUP_BY_OPTIONS = frozenset({"timeframe", "scan", "indicator", "scan_tf"})


def _group_key(row: TrackPosition, group_by: str) -> str:
    scan = (row.source_label or "Adsız tarama").strip() or "Adsız tarama"
    tf = (row.timeframe or "—").strip() or "—"
    if group_by == "scan":
        return scan
    if group_by == "indicator":
        return (row.indicator_label or "Teknik filtreler").strip() or "Teknik filtreler"
    if group_by == "scan_tf":
        return f"{scan} · {tf}"
    return tf


def _group_label(key: str, group_by: str) -> str:
    if group_by == "timeframe":
        return TIMEFRAME_LABELS.get(key, key)
    if group_by == "scan_tf" and " · " in key:
        scan, tf = key.rsplit(" · ", 1)
        return f"{scan} · {TIMEFRAME_LABELS.get(tf, tf)}"
    return key


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 3)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        try:
            dt = datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _dedupe_first_symbol(rows: list[TrackPosition]) -> list[TrackPosition]:
    ordered = sorted(rows, key=lambda r: r.entry_at or datetime.min.replace(tzinfo=timezone.utc))
    seen: set[tuple[str, str]] = set()
    kept: list[TrackPosition] = []
    for row in ordered:
        key = ((row.symbol or "").upper(), (row.universe or "").lower())
        if key in seen:
            continue
        seen.add(key)
        kept.append(row)
    return kept


def performance_report(
    db: Session,
    user_id: int,
    *,
    group_by: str = "timeframe",
    date_from: str | None = None,
    date_to: str | None = None,
    include_positions: bool = False,
    dedupe: str | None = None,
) -> dict[str, Any]:
    group_by = group_by if group_by in GROUP_BY_OPTIONS else "timeframe"
    start = _parse_dt(date_from)
    end = _parse_dt(date_to)
    q = db.query(TrackPosition).filter(TrackPosition.user_id == user_id)
    if start is not None:
        q = q.filter(TrackPosition.entry_at >= start)
    if end is not None:
        if end.hour == 0 and end.minute == 0 and end.second == 0 and len((date_to or "")[:10]) == 10:
            end = end.replace(hour=23, minute=59, second=59)
        q = q.filter(TrackPosition.entry_at <= end)

    rows = q.order_by(TrackPosition.entry_at.desc()).all()
    if (dedupe or "").lower() == "symbol":
        rows = _dedupe_first_symbol(rows)

    buckets: dict[str, list[TrackPosition]] = defaultdict(list)
    for row in rows:
        buckets[_group_key(row, group_by)].append(row)

    groups: list[dict[str, Any]] = []
    for key, items in buckets.items():
        settled = [r for r in items if r.status not in WATCH_STATUSES]
        open_n = len(items) - len(settled)
        r_values = [v for r in settled if (v := realized_r(r)) is not None]
        wins = [v for v in r_values if v > 0]
        losses = [v for v in r_values if v < 0]
        tp_n = sum(1 for r in items if r.first_tp_at or r.status in {"after_tp", "opposite_signal", "hit_target"})
        sl_n = sum(1 for r in items if r.first_sl_at or r.status == "hit_stop")
        n = len(items)
        settled_n = len(settled)
        win_rate = (tp_n / settled_n * 100) if settled_n else 0.0
        sl_rate = (sl_n / settled_n * 100) if settled_n else 0.0
        expected = _avg(r_values)
        mfes: list[float] = []
        maes: list[float] = []
        tp_hours: list[float] = []
        sl_hours: list[float] = []
        hold: list[float] = []
        for row in items:
            mfe, mae = excursion_pcts(row)
            if mfe is not None:
                mfes.append(mfe)
            if mae is not None:
                maes.append(mae)
            if row.hours_to_tp is not None:
                tp_hours.append(float(row.hours_to_tp))
            if row.hours_to_sl is not None:
                sl_hours.append(float(row.hours_to_sl))
            if row.exit_at:
                hours = _hours_between(row.entry_at, row.exit_at)
                if hours is not None:
                    hold.append(hours)
        rank_ready = settled_n >= MIN_SAMPLE_FOR_RANK
        groups.append(
            {
                "key": key,
                "label": _group_label(key, group_by),
                "count": n,
                "open_count": open_n,
                "settled_count": settled_n,
                "tp_count": tp_n,
                "sl_count": sl_n,
                "opposite_count": sum(1 for r in items if r.status == "opposite_signal"),
                "archived_count": sum(1 for r in items if r.status == "archived"),
                "win_rate": round(win_rate, 2),
                "sl_rate": round(sl_rate, 2),
                "expected_r": expected,
                "avg_win_r": _avg(wins),
                "avg_loss_r": _avg([-v for v in losses]) if losses else None,
                "avg_mfe_pct": _avg(mfes) or 0.0,
                "avg_mae_pct": _avg(maes) or 0.0,
                "avg_hours_to_tp": _avg(tp_hours),
                "avg_hours_to_sl": _avg(sl_hours),
                "avg_hold_hours": _avg(hold),
                "rank_ready": rank_ready,
                "insufficient": not rank_ready,
            }
        )

    groups.sort(
        key=lambda g: (
            g["rank_ready"],
            g["expected_r"] if g["expected_r"] is not None else -999,
            g["settled_count"],
            g["avg_mfe_pct"],
        ),
        reverse=True,
    )
    rank = 0
    for item in groups:
        if item["rank_ready"]:
            rank += 1
            item["rank"] = rank
        else:
            item["rank"] = None

    out: dict[str, Any] = {
        "group_by": group_by,
        "date_from": date_from,
        "date_to": date_to,
        "dedupe": dedupe,
        "total": len(rows),
        "min_sample": MIN_SAMPLE_FOR_RANK,
        "level_benchmarks": level_benchmarks_for_api(),
        "groups": groups,
    }
    if include_positions:
        out["positions"] = [position_to_dict(r) for r in rows[:800]]
    return out
