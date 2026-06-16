"""Gedhusek TrendFibonacci-style first green bar signal."""

from __future__ import annotations

import re

import pandas as pd

from app.services import indicators as ind
from app.services.pine_params import merge_pine_inputs

FIBO_MARKER = "__CANDLE_GREEN_FIRST__"


def _parse_wma_length(code: str) -> int:
    m = re.search(r"ta\.wma\s*\(\s*close\s*,\s*(\d+)\s*\)", code, flags=re.I)
    return int(m.group(1)) if m else 6


def _parse_indicator_title(code: str) -> str:
    m = re.search(r'indicator\s*\(\s*"([^"]+)"', code, flags=re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r'shorttitle\s*=\s*"([^"]+)"', code, flags=re.I)
    return m.group(1).strip() if m else "Fibo Trend"


def fibo_trend_series(
    df: pd.DataFrame,
    back_step: int = 50,
    lower_value: float = 0.382,
    upper_value: float = 0.618,
    wma_length: int = 6,
) -> dict[str, pd.Series]:
    """Compute green / first-green series (Pine-equivalent)."""
    c = df["Close"]
    mx = ind.highest(c, back_step)
    mn = ind.lowest(c, back_step)
    upper_fib = mn + (mx - mn) * upper_value
    ma = ind.wma(c, wma_length)
    green = ma > upper_fib
    prev = green.shift(1)
    first_green = green & (~prev.fillna(False).astype(bool))
    return {
        "ma": ma,
        "upper_fib": upper_fib,
        "green": green,
        "first_green": first_green,
    }


def fibo_trend_first_green(
    df: pd.DataFrame,
    back_step: int = 50,
    lower_value: float = 0.382,
    upper_value: float = 0.618,
    wma_length: int = 6,
) -> bool:
    """True only on the bar where candle turns green (not while staying green)."""
    series = fibo_trend_series(df, back_step, lower_value, upper_value, wma_length)
    fg = series["first_green"]
    if fg.empty:
        return False
    return bool(fg.iloc[-1]) if pd.notna(fg.iloc[-1]) else False


def fibo_trend_snapshot(
    df: pd.DataFrame,
    back_step: int = 50,
    lower_value: float = 0.382,
    upper_value: float = 0.618,
    wma_length: int = 6,
) -> dict[str, bool | float]:
    """Latest-bar diagnostics for API / debugging."""
    if df is None or len(df) < back_step + 2:
        return {"first_green_bar": False, "green_now": False}
    s = fibo_trend_series(df, back_step, lower_value, upper_value, wma_length)
    green_now = bool(s["green"].iloc[-1]) if pd.notna(s["green"].iloc[-1]) else False
    first = bool(s["first_green"].iloc[-1]) if pd.notna(s["first_green"].iloc[-1]) else False
    return {
        "first_green_bar": first,
        "green_now": green_now,
        "ma": float(s["ma"].iloc[-1]) if pd.notna(s["ma"].iloc[-1]) else None,
        "upper_fib": float(s["upper_fib"].iloc[-1]) if pd.notna(s["upper_fib"].iloc[-1]) else None,
    }


def fibo_params_from_script(
    pine_code: str, overrides: dict | None = None
) -> dict[str, int | float]:
    inputs = merge_pine_inputs(pine_code, overrides)
    return {
        "back_step": int(float(inputs.get("BackStep", 50))),
        "lower_value": float(inputs.get("lowerValue", 0.382)),
        "upper_value": float(inputs.get("upperValue", 0.618)),
        "wma_length": _parse_wma_length(pine_code),
    }


def fibo_first_green_from_script(
    df: pd.DataFrame, pine_code: str, pine_input_overrides: dict | None = None
) -> bool:
    p = fibo_params_from_script(pine_code, pine_input_overrides)
    return fibo_trend_first_green(df, **p)


def fibo_display_label(pine_code: str) -> str:
    title = _parse_indicator_title(pine_code)
    p = fibo_params_from_script(pine_code)
    return (
        f"İlk yeşil mum — {title} "
        f"(WMA {p['wma_length']}, periyot {p['back_step']}, üst Fib {p['upper_value']})"
    )
