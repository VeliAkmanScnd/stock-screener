"""Technical indicators for screening (Pine-compatible where noted)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def sma(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(length).mean()


def wma(series: pd.Series, length: int) -> pd.Series:
    """Weighted moving average (Pine ta.wma)."""
    weights = np.arange(1, length + 1, dtype=float)
    return series.rolling(length).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)


def highest(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(int(length)).max()


def lowest(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(int(length)).min()


def rsi(close: pd.Series, length: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def cci(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 20) -> pd.Series:
    tp = (high + low + close) / 3
    sma_tp = tp.rolling(length).mean()
    mad = tp.rolling(length).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    return (tp - sma_tp) / (0.015 * mad.replace(0, np.nan))


def atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / length, adjust=False).mean()


def adx(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    up = high.diff()
    down = -low.diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    atr_vals = atr(high, low, close, length)
    plus_di = 100 * pd.Series(plus_dm, index=close.index).ewm(alpha=1 / length, adjust=False).mean() / atr_vals
    minus_di = 100 * pd.Series(minus_dm, index=close.index).ewm(alpha=1 / length, adjust=False).mean() / atr_vals
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / length, adjust=False).mean()


def momentum(close: pd.Series, length: int = 10) -> pd.Series:
    return close - close.shift(length)


def alma(close: pd.Series, length: int = 9, offset: float = 0.85, sigma: float = 6.0) -> pd.Series:
    """Arnaud Legoux Moving Average (Pine ta.alma approximation)."""
    m = offset * (length - 1)
    s = length / sigma
    weights = np.array([np.exp(-((i - m) ** 2) / (2 * s * s)) for i in range(length)])
    weights /= weights.sum()

    def _alma(window: np.ndarray) -> float:
        return float(np.dot(window, weights))

    return close.rolling(length).apply(_alma, raw=True)


def crossover(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a > b) & (a.shift(1) <= b.shift(1))


def crossunder(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a < b) & (a.shift(1) >= b.shift(1))


def build_indicator_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Attach standard indicators to OHLCV dataframe."""
    out = df.copy()
    c, h, l = out["Close"], out["High"], out["Low"]

    for period in (9, 12, 20, 21, 26, 50, 100, 200):
        out[f"ema_{period}"] = ema(c, period)

    out["alma_9"] = alma(c, 9)
    out["alma_21"] = alma(c, 21)
    out["rsi_14"] = rsi(c, 14)
    out["adx_14"] = adx(h, l, c, 14)
    out["atr_14"] = atr(h, l, c, 14)
    out["cci_20"] = cci(h, l, c, 20)
    out["mom_10"] = momentum(c, 10)
    out["sma_20"] = sma(c, 20)
    out["sma_50"] = sma(c, 50)

    return out
