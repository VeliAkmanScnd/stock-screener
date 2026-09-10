"""BigBeluga-style market structure / ChoCh bullish flip detection."""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from app.services import indicators as ind
from app.services.pine_params import merge_pine_inputs

CHOCH_BULLISH_MARKER = "__CHOCH_BULLISH_FIRST__"


def _parse_indicator_title(code: str) -> str:
    m = re.search(r'indicator\s*\(\s*"([^"]+)"', code, flags=re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r'shorttitle\s*=\s*"([^"]+)"', code, flags=re.I)
    return m.group(1).strip() if m else "Market Structure"


def is_choch_market_structure_script(code: str) -> bool:
    """Detect pivot + ChoCh / direction flip scripts (e.g. BigBeluga MS Trend Matrix)."""
    raw = re.sub(r"//.*?$", "", code, flags=re.MULTILINE)
    has_pivot = bool(
        re.search(r"ta\.pivothigh\s*\(", raw, flags=re.I)
        and re.search(r"ta\.pivotlow\s*\(", raw, flags=re.I)
    )
    has_choch = bool(re.search(r"ChoCh", raw, flags=re.I))
    has_direction_flip = bool(
        re.search(r"ta\.crossover\s*\(\s*close\s*,\s*phVal\s*\)\s*and\s*not\s*direction", raw, flags=re.I)
        or re.search(r"direction\s*!=\s*direction\s*\[\s*1\s*\]", raw, flags=re.I)
    )
    has_ms_title = bool(re.search(r"market\s*structure|trend\s*matrix", raw, flags=re.I))
    return has_pivot and (has_choch or has_direction_flip or has_ms_title)


def choch_params_from_script(pine_code: str, overrides: dict | None = None) -> dict[str, int]:
    inputs = merge_pine_inputs(pine_code, overrides)
    ms_len = int(float(inputs.get("msLen", 10)))
    return {"ms_len": max(2, ms_len)}


def _pivothigh(series: pd.Series, left: int, right: int) -> pd.Series:
    out = pd.Series(np.nan, index=series.index, dtype=float)
    for i in range(left + right, len(series)):
        center = i - right
        window = series.iloc[center - left : center + right + 1]
        if len(window) < left + right + 1:
            continue
        val = series.iloc[center]
        if pd.notna(val) and val == window.max():
            out.iloc[i] = float(val)
    return out


def _pivotlow(series: pd.Series, left: int, right: int) -> pd.Series:
    out = pd.Series(np.nan, index=series.index, dtype=float)
    for i in range(left + right, len(series)):
        center = i - right
        window = series.iloc[center - left : center + right + 1]
        if len(window) < left + right + 1:
            continue
        val = series.iloc[center]
        if pd.notna(val) and val == window.min():
            out.iloc[i] = float(val)
    return out


def choch_direction_series(df: pd.DataFrame, ms_len: int = 10) -> pd.Series:
    """Replay Pine direction state (bullish=True after ChoCh ↑)."""
    h = df["High"]
    l = df["Low"]
    c = df["Close"]
    ph = _pivothigh(h, ms_len, ms_len)
    pl = _pivotlow(l, ms_len, ms_len)

    ph_val = np.nan
    pl_val = np.nan
    direction = False
    directions: list[bool] = []

    for i in range(len(df)):
        if pd.notna(ph.iloc[i]):
            pivot_idx = i - ms_len
            if pivot_idx >= 0:
                ph_val = float(h.iloc[pivot_idx])
        if pd.notna(pl.iloc[i]):
            pivot_idx = i - ms_len
            if pivot_idx >= 0:
                pl_val = float(l.iloc[pivot_idx])

        if i > 0:
            prev_close = float(c.iloc[i - 1])
            cur_close = float(c.iloc[i])
            if pd.notna(ph_val) and prev_close <= ph_val and cur_close > ph_val and not direction:
                direction = True
            if pd.notna(pl_val) and prev_close >= pl_val and cur_close < pl_val and direction:
                direction = False

        directions.append(direction)

    return pd.Series(directions, index=df.index, dtype=bool)


def choch_bullish_first_bar(df: pd.DataFrame, ms_len: int = 10) -> bool:
    """True on the first bar of bullish ChoCh (direction flips to True)."""
    if df is None or len(df) < ms_len * 2 + 3:
        return False
    direction = choch_direction_series(df, ms_len)
    if len(direction) < 2:
        return False
    cur = bool(direction.iloc[-1])
    prev = bool(direction.iloc[-2])
    return cur and not prev


def choch_bullish_from_script(
    df: pd.DataFrame, pine_code: str, pine_input_overrides: dict | None = None
) -> bool:
    params = choch_params_from_script(pine_code, pine_input_overrides)
    return choch_bullish_first_bar(df, **params)


def choch_display_label(pine_code: str) -> str:
    title = _parse_indicator_title(pine_code)
    ms_len = choch_params_from_script(pine_code)["ms_len"]
    return f"ChoCh ↑ (yükseliş yapısı) — {title} (MS uzunluk {ms_len})"
