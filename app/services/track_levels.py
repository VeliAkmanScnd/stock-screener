"""Timeframe TP/SL benchmarks and R-multiple helpers."""

from __future__ import annotations

from typing import Any

TIMEFRAME_LEVEL_BENCHMARKS: dict[str, dict[str, Any]] = {
    "5m": {"target_pct": 1.5, "stop_pct": 1.0, "label": "5 dakika", "featured": False},
    "15m": {"target_pct": 2.0, "stop_pct": 1.5, "label": "15 dakika", "featured": True},
    "30m": {"target_pct": 2.5, "stop_pct": 1.8, "label": "30 dakika", "featured": False},
    "1h": {"target_pct": 3.0, "stop_pct": 2.0, "label": "1 saat", "featured": True},
    "2h": {"target_pct": 4.0, "stop_pct": 2.5, "label": "2 saat", "featured": False},
    "4h": {"target_pct": 5.0, "stop_pct": 3.0, "label": "4 saat", "featured": False},
    "8h": {"target_pct": 6.0, "stop_pct": 3.5, "label": "8 saat", "featured": False},
    "12h": {"target_pct": 7.0, "stop_pct": 4.0, "label": "12 saat", "featured": False},
    "1d": {"target_pct": 8.0, "stop_pct": 5.0, "label": "1 gün", "featured": True},
    "1wk": {"target_pct": 12.0, "stop_pct": 7.0, "label": "1 hafta", "featured": False},
}

MIN_SAMPLE_FOR_RANK = 20


def levels_for_timeframe(timeframe: str | None) -> tuple[float, float]:
    row = TIMEFRAME_LEVEL_BENCHMARKS.get((timeframe or "1d").strip()) or TIMEFRAME_LEVEL_BENCHMARKS["1d"]
    return float(row["target_pct"]), float(row["stop_pct"])


def level_benchmarks_for_api() -> list[dict[str, Any]]:
    out = []
    for key, row in TIMEFRAME_LEVEL_BENCHMARKS.items():
        target = float(row["target_pct"])
        stop = float(row["stop_pct"])
        out.append(
            {
                "timeframe": key,
                "label": row["label"],
                "target_pct": target,
                "stop_pct": stop,
                "r_multiple": round(target / stop, 2) if stop else None,
                "featured": bool(row.get("featured")),
            }
        )
    return out


def realized_r(row: Any) -> float | None:
    stop = float(getattr(row, "stop_pct", 0) or 0) or 1.0
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
    return round(pnl_pct / stop, 3)
