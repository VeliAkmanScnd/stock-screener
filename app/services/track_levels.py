"""Timeframe TP/SL benchmarks and R-multiple helpers."""

from __future__ import annotations

from typing import Any

# Take-profit is 1.7 times the stop distance on every timeframe.
TARGET_R = 1.7

TIMEFRAME_LEVEL_BENCHMARKS: dict[str, dict[str, Any]] = {
    "3m": {"stop_pct": 0.6, "label": "3 dakika", "featured": False},
    "5m": {"stop_pct": 1.0, "label": "5 dakika", "featured": False},
    "15m": {"stop_pct": 1.5, "label": "15 dakika", "featured": True},
    "30m": {"stop_pct": 1.8, "label": "30 dakika", "featured": False},
    "1h": {"stop_pct": 2.0, "label": "1 saat", "featured": True},
    "2h": {"stop_pct": 2.5, "label": "2 saat", "featured": False},
    "4h": {"stop_pct": 3.0, "label": "4 saat", "featured": False},
    "8h": {"stop_pct": 3.5, "label": "8 saat", "featured": False},
    "12h": {"stop_pct": 4.0, "label": "12 saat", "featured": False},
    "1d": {"stop_pct": 5.0, "label": "1 gün", "featured": True},
    "1wk": {"stop_pct": 7.0, "label": "1 hafta", "featured": False},
}

MIN_SAMPLE_FOR_RANK = 20


def target_pct_for_stop(stop_pct: float) -> float:
    return round(float(stop_pct) * TARGET_R, 2)


def levels_for_timeframe(timeframe: str | None) -> tuple[float, float]:
    row = TIMEFRAME_LEVEL_BENCHMARKS.get((timeframe or "1d").strip()) or TIMEFRAME_LEVEL_BENCHMARKS["1d"]
    stop = float(row["stop_pct"])
    return target_pct_for_stop(stop), stop


def level_benchmarks_for_api() -> list[dict[str, Any]]:
    out = []
    for key, row in TIMEFRAME_LEVEL_BENCHMARKS.items():
        stop = float(row["stop_pct"])
        out.append(
            {
                "timeframe": key,
                "label": row["label"],
                "target_pct": target_pct_for_stop(stop),
                "stop_pct": stop,
                "r_multiple": TARGET_R,
                "featured": bool(row.get("featured")),
            }
        )
    return out


def reward_r(move_pct: float | None, stop_pct: float | None) -> float | None:
    """R multiple of a percent move against the position's stop distance."""
    if move_pct is None:
        return None
    try:
        stop = float(stop_pct or 0)
        move = float(move_pct)
    except (TypeError, ValueError):
        return None
    if stop <= 0 or move != move:
        return None
    return round(move / stop, 3)


def realized_r(row: Any) -> float | None:
    entry = getattr(row, "entry_price", None)
    exit_px = getattr(row, "exit_price", None)
    if exit_px is None:
        exit_px = getattr(row, "current_price", None)
    if not entry or exit_px is None:
        return None
    direction = (getattr(row, "direction", None) or "AL").upper()
    if direction == "SAT":
        pnl_pct = (entry - exit_px) / entry * 100
    else:
        pnl_pct = (exit_px - entry) / entry * 100
    stop = getattr(row, "stop_pct", None) or 1.0
    return reward_r(pnl_pct, stop)
