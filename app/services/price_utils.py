"""Shared helpers for reading latest close prices from OHLCV frames."""

from __future__ import annotations

import pandas as pd


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


def yf_frame_for_ticker(raw: pd.DataFrame, yf_symbol: str) -> pd.DataFrame:
    if raw is None or raw.empty:
        return raw
    if isinstance(raw.columns, pd.MultiIndex):
        return raw.xs(yf_symbol, axis=1, level=0, drop_level=True)
    return raw
