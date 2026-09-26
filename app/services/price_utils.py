"""Shared helpers for reading latest close prices from OHLCV frames."""

from __future__ import annotations

import pandas as pd


def _named_series(df, names: tuple[str, ...]):
    wanted = {n.lower() for n in names}
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        level = -1
        labels = [str(x) for x in df.columns.get_level_values(level)]
        match = next((lab for lab in labels if lab.lower() in wanted), None)
        if match is None:
            return None
        series = df.xs(match, axis=1, level=level)
        return series.iloc[:, 0] if isinstance(series, pd.DataFrame) else series
    col = next((c for c in df.columns if str(c).lower() in wanted), None)
    return df[col] if col is not None else None


def last_close_price(df) -> float | None:
    if df is None or df.empty:
        return None

    if isinstance(df.columns, pd.MultiIndex):
        level = -1
        names = df.columns.get_level_values(level)
        if "Close" in names:
            close = df.xs("Close", axis=1, level=level)
        elif "close" in names:
            close = df.xs("close", axis=1, level=level)
        else:
            return None
        series = close.iloc[:, 0] if isinstance(close, pd.DataFrame) else close
    else:
        col = next((c for c in df.columns if str(c).lower() == "close"), None)
        if col is None:
            col = next((c for c in df.columns if str(c).lower() == "adj close"), None)
        if col is None:
            return None
        series = df[col]

    for val in series.iloc[::-1]:
        if val == val:
            return float(val)
    return None


def last_quote(df, lookback: int = 8) -> dict[str, float] | None:
    last = last_close_price(df)
    if last is None:
        return None
    high_s = _named_series(df, ("high",))
    low_s = _named_series(df, ("low",))
    high = last
    low = last
    if high_s is not None and not high_s.empty:
        tail = high_s.tail(lookback).dropna()
        if not tail.empty:
            high = float(tail.max())
    if low_s is not None and not low_s.empty:
        tail = low_s.tail(lookback).dropna()
        if not tail.empty:
            low = float(tail.min())
    return {"last": last, "high": high, "low": low}


def yf_frame_for_ticker(raw: pd.DataFrame, yf_symbol: str) -> pd.DataFrame:
    if raw is None or raw.empty:
        return raw
    if isinstance(raw.columns, pd.MultiIndex):
        return raw.xs(yf_symbol, axis=1, level=0, drop_level=True)
    return raw
