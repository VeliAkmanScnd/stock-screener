"""Use the last confirmed (closed) bar — skip the still-forming candle."""

from __future__ import annotations

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
