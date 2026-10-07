"""Use the last confirmed (closed) bar — skip the still-forming candle."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from app.services.ticker_format import is_bist_universe, is_viop_universe

TIMEFRAME_SECONDS: dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "8h": 28800,
    "12h": 43200,
    "1d": 86400,
    "1wk": 7 * 86400,
}


def market_timezone(universe: str | None) -> str:
    u = (universe or "").lower()
    if is_bist_universe(u) or is_viop_universe(u):
        return "Europe/Istanbul"
    if u in ("binance", "binance_spot", "crypto"):
        return "UTC"
    return "America/New_York"


def timeframe_seconds(timeframe: str) -> int:
    return TIMEFRAME_SECONDS.get((timeframe or "1d").strip().lower(), 86400)


def _to_market_ts(
    value: Any,
    *,
    universe: str | None = None,
) -> pd.Timestamp | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        ts = pd.Timestamp(value)
    except (TypeError, ValueError):
        return None
    if ts is pd.NaT:
        return None
    tz_name = market_timezone(universe)
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")
    if ts.tzinfo is None:
        try:
            ts = ts.tz_localize(tz)
        except Exception:
            ts = ts.tz_localize("UTC").tz_convert(tz)
    else:
        ts = ts.tz_convert(tz)
    return ts


def format_bar_label(
    value: Any,
    timeframe: str | None = None,
    *,
    universe: str | None = None,
) -> str | None:
    """Human label for the signal bar, e.g. '15:00 barı' or '07.10.2026 barı'."""
    ts = _to_market_ts(value, universe=universe)
    if ts is None:
        return None
    tf = (timeframe or "1d").strip().lower()
    secs = timeframe_seconds(tf)
    local = ts.to_pydatetime()
    if secs < 86400:
        now = datetime.now(tz=local.tzinfo)
        clock = local.strftime("%H:%M")
        if local.date() == now.date():
            return f"{clock} barı"
        return f"{local.strftime('%d.%m.%Y')} {clock} barı"
    if tf in ("1wk", "1w", "week", "weekly"):
        return f"{local.strftime('%d.%m.%Y')} (haftalık) barı"
    return f"{local.strftime('%d.%m.%Y')} barı"


def signal_bar_fields(
    df: pd.DataFrame | None,
    timeframe: str | None = None,
    *,
    universe: str | None = None,
) -> dict[str, str]:
    """ISO + display fields for the last confirmed bar on ``df``."""
    if df is None or len(df) < 1:
        return {}
    ts = _to_market_ts(df.index[-1], universe=universe)
    if ts is None:
        return {}
    label = format_bar_label(ts, timeframe, universe=universe)
    out = {"bar_time": ts.isoformat()}
    if label:
        out["bar_label"] = label
    return out


def drop_unclosed_bar(
    df: pd.DataFrame,
    timeframe: str,
    *,
    universe: str | None = None,
) -> pd.DataFrame:
    """Drop the last row when that candle has not finished yet."""
    if df is None or len(df) < 2:
        return df
    ts = pd.Timestamp(df.index[-1])
    hint = market_timezone(universe)
    if ts.tzinfo is None:
        try:
            ts = ts.tz_localize(hint)
        except Exception:
            ts = ts.tz_localize("UTC")
    now = pd.Timestamp.now(tz=ts.tz)
    close_at = ts + pd.Timedelta(seconds=timeframe_seconds(timeframe))
    if now + pd.Timedelta(seconds=5) < close_at:
        return df.iloc[:-1]
    return df
