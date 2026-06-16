"""Merged-Triple Confluence Pine script — full bar replay for screening."""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from app.services import indicators as ind
from app.services.pine_params import merge_pine_inputs

MERGED_TRIPLE_MARKER = "__MERGED_TRIPLE_BUY__"


def is_merged_triple_script(pine_code: str) -> bool:
    if re.search(r'indicator\s*\(\s*"Merged-Triple', pine_code, flags=re.I):
        return True
    return "Merged-Triple Confluence" in pine_code or "Merged-Triple" in pine_code[:500]


def _parse_bool(val: str, default: bool) -> bool:
    v = val.strip().lower()
    if v in ("true", "1"):
        return True
    if v in ("false", "0"):
        return False
    return default


def merged_params_from_script(pine_code: str, overrides: dict | None = None) -> dict:
    inp = merge_pine_inputs(pine_code, overrides)
    return {
        "confluence_window": int(float(inp.get("confluenceWindow", 0))),
        "require_alma_color": _parse_bool(inp.get("requireAlmaColor", "true"), True),
        "require_bull_bar": _parse_bool(inp.get("requireBullBar", "true"), True),
        "avoid_repeats": _parse_bool(inp.get("avoidRepeats", "true"), True),
        "use_ema_filter": _parse_bool(inp.get("useEmaFilter", "false"), False),
        "alma_len": int(float(inp.get("alma_len", 24))),
        "alma_offset": float(inp.get("alma_offset", 0.7)),
        "alma_sigma": float(inp.get("alma_sigma", 4)),
        "per_len": int(float(inp.get("per_len", 21))),
        "med_len": int(float(inp.get("med_len", 21))),
        "med_mult": float(inp.get("med_mult", 1.8)),
        "iu_length": int(float(inp.get("iu_length", 10))),
        "iu_trend_length": int(float(inp.get("iu_trend_length", 50))),
        "iu_rsi_length": int(float(inp.get("iu_rsi_length", 14))),
        "roc_len": int(float(inp.get("rocLen", 55))),
        "ma_len": int(float(inp.get("maLen", 7))),
        "sig_len": int(float(inp.get("sigLen", 9))),
        "neutral_thr": float(inp.get("neutralThr", 0.5)),
        "roc_ma_type": inp.get("roc_ma_type", "TEMA").strip('"'),
        "ema_len": int(float(inp.get("ema_len", 20))),
    }


def _hlcc4(df: pd.DataFrame) -> pd.Series:
    h, l, c = df["High"], df["Low"], df["Close"]
    return (h + l + c + c) / 4


def _rma(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(alpha=1 / length, adjust=False).mean()


def _stdev(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(length).std()


def _linreg(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(length).apply(
        lambda y: np.polyfit(np.arange(len(y)), y, 1)[0] * (len(y) - 1) + np.polyfit(np.arange(len(y)), y, 1)[1],
        raw=True,
    )


def _tema(source: pd.Series, length: int) -> pd.Series:
    e1 = ind.ema(source, length)
    e2 = ind.ema(e1, length)
    e3 = ind.ema(e2, length)
    return 3 * (e1 - e2) + e3


def _dema(source: pd.Series, length: int) -> pd.Series:
    e1 = ind.ema(source, length)
    e2 = ind.ema(e1, length)
    return 2 * e1 - e2


def _hma(source: pd.Series, length: int) -> pd.Series:
    half = max(1, length // 2)
    sqrt_l = max(1, int(np.sqrt(length)))
    return ind.wma(2 * ind.wma(source, half) - ind.wma(source, length), sqrt_l)


def _ma(source: pd.Series, length: int, ma_type: str) -> pd.Series:
    t = ma_type.upper()
    if t == "SMA":
        return ind.sma(source, length)
    if t == "EMA":
        return ind.ema(source, length)
    if t == "SMMA":
        return _rma(source, length)
    if t == "WMA":
        return ind.wma(source, length)
    if t == "VWMA":
        # No volume weighting in screener — fallback to WMA
        return ind.wma(source, length)
    if t == "TEMA":
        return _tema(source, length)
    if t == "DEMA":
        return _dema(source, length)
    if t == "LSMA":
        return _linreg(source, length)
    if t == "HMA":
        return _hma(source, length)
    if t == "ALMA":
        return ind.alma(source, length, 0.85, 6)
    return ind.ema(source, length)


def _percentile_nearest_rank(series: pd.Series, length: int, pct: float) -> pd.Series:
    q = pct / 100.0
    return series.rolling(length, min_periods=length).quantile(q, interpolation="nearest")


def _barssince(cond: pd.Series) -> pd.Series:
    """Bars since last True (NaN if never)."""
    n = len(cond)
    out = np.full(n, np.nan)
    last = -1
    for i in range(n):
        if bool(cond.iloc[i]):
            last = i
        if last >= 0:
            out[i] = i - last
    return pd.Series(out, index=cond.index)


def _within(cond: pd.Series, window: int) -> pd.Series:
    bs = _barssince(cond)
    return bs.notna() & (bs <= window)


def merged_triple_buy_series(df: pd.DataFrame, **params) -> pd.Series:
    """Replay Merged-Triple logic; return buyFlip series."""
    c = df["Close"]
    o = df["Open"]
    h = df["High"]
    l = df["Low"]
    n = len(df)
    if n < max(params["roc_len"], params["iu_trend_length"], params["alma_len"]) + 5:
        return pd.Series(False, index=df.index)

    alma_val = ind.alma(c, params["alma_len"], params["alma_offset"], params["alma_sigma"])
    p75 = _percentile_nearest_rank(alma_val, params["per_len"], 75)
    p25 = _percentile_nearest_rank(alma_val, params["per_len"], 25)

    alma_median = c.rolling(params["med_len"]).median()
    alma_med_abs = (c - alma_median).abs()
    alma_filter = alma_med_abs.rolling(params["med_len"]).median()
    alma_long_f = alma_filter * params["med_mult"]
    alma_short_f = alma_filter

    alma_long_c = c > (p75 + alma_long_f)
    alma_short_c = c < (p25 - alma_short_f)

    qb = np.zeros(n, dtype=int)
    for i in range(n):
        if bool(alma_long_c.iloc[i]) and not bool(alma_short_c.iloc[i]):
            qb[i] = 1
        elif bool(alma_short_c.iloc[i]):
            qb[i] = -1
        else:
            qb[i] = qb[i - 1] if i else 0
    alma_col_buy = pd.Series(qb == 1, index=df.index)

    # IU Smart Flow
    iu_len = params["iu_length"]
    iu_bull_imb = ind.highest(c, iu_len) - c.shift(iu_len)
    iu_bear_imb = c.shift(iu_len) - ind.lowest(c, iu_len)
    iu_atr = ind.atr(h, l, c, 14)
    iu_ofs = iu_bull_imb - iu_bear_imb
    iu_bull_trend = ind.sma(c, params["iu_trend_length"]) + iu_atr
    iu_bear_trend = ind.sma(c, params["iu_trend_length"]) - iu_atr
    iu_trend_up = c > iu_bull_trend
    iu_trend_down = c < iu_bear_trend
    iu_rsi = ind.rsi(c, params["iu_rsi_length"])

    iu_long_entry = np.zeros(n, dtype=bool)
    iu_short_entry = np.zeros(n, dtype=bool)
    iu_in_long = False
    iu_in_short = False
    for i in range(n):
        if (
            pd.notna(iu_ofs.iloc[i])
            and iu_ofs.iloc[i] > 0
            and bool(iu_trend_up.iloc[i])
            and iu_rsi.iloc[i] > 50
            and not iu_in_long
        ):
            iu_long_entry[i] = True
            iu_in_long = True
            iu_in_short = False
        if (
            pd.notna(iu_ofs.iloc[i])
            and iu_ofs.iloc[i] < 0
            and bool(iu_trend_down.iloc[i])
            and iu_rsi.iloc[i] < 50
            and not iu_in_short
        ):
            iu_short_entry[i] = True
            iu_in_short = True
            iu_in_long = False
    iu_long_s = pd.Series(iu_long_entry, index=df.index)
    iu_short_s = pd.Series(iu_short_entry, index=df.index)

    # ROCWMA
    roc_src = _hlcc4(df)
    roc_len = params["roc_len"]
    roc_val = roc_src.pct_change(roc_len) * 100
    roc_low = roc_val.rolling(roc_len).min()
    roc_high = roc_val.rolling(roc_len).max()
    denom = (roc_high - roc_low).replace(0, np.nan)
    roc_norm = (roc_val - roc_low) / denom
    roc_base = _ma(roc_src, params["ma_len"], params["roc_ma_type"])
    roc_wdiff = roc_norm * (roc_src - roc_base)
    rwma = roc_base + roc_wdiff
    roc_osc = (rwma - ind.sma(rwma, roc_len)) / _stdev(rwma, roc_len).replace(0, np.nan)
    roc_sig = ind.ema(roc_osc, params["sig_len"])
    _ = roc_sig  # parity with Pine; signal uses osc colors

    thr = params["neutral_thr"]
    roc_cur = np.zeros(n, dtype=int)  # 1 bull, -1 bear, 0 neutral
    roc_long_arr = np.zeros(n, dtype=bool)
    roc_short_arr = np.zeros(n, dtype=bool)
    prev_col = 0
    for i in range(n):
        osc = roc_osc.iloc[i]
        if pd.isna(osc):
            cur = prev_col
        elif -thr < osc < thr:
            cur = prev_col
        elif osc > thr:
            cur = 1
        elif osc < -thr:
            cur = -1
        else:
            cur = 0
        roc_long_arr[i] = cur == 1 and prev_col == -1
        roc_short_arr[i] = cur == -1 and prev_col == 1
        roc_cur[i] = cur
        prev_col = cur
    roc_long = pd.Series(roc_long_arr, index=df.index)
    roc_short = pd.Series(roc_short_arr, index=df.index)

    w = params["confluence_window"]
    buy_conf = (roc_long & _within(iu_long_s, w)) | (iu_long_s & _within(roc_long, w))
    sell_conf = (roc_short & _within(iu_short_s, w)) | (iu_short_s & _within(roc_short, w))
    _ = sell_conf

    price_above = (c > p75) & (c > p25)
    alma_buy_ok = (~params["require_alma_color"]) | alma_col_buy
    bar_buy_ok = (~params["require_bull_bar"]) | (c > o)

    ema_high = ind.ema(h, params["ema_len"])
    ema_low = ind.ema(l, params["ema_len"])
    ema_buy_ok = (not params["use_ema_filter"]) | ((c > ema_high) & (c > ema_low))

    # Daily scan: skip Istanbul intraday time filter (not meaningful on 1D bars)
    signals_allowed = pd.Series(True, index=df.index)

    buy_signal = buy_conf & price_above & alma_buy_ok & bar_buy_ok & ema_buy_ok & signals_allowed

    final_state = 0
    buy_flip = np.zeros(n, dtype=bool)
    for i in range(n):
        bf = bool(buy_signal.iloc[i]) and (
            not params["avoid_repeats"] or final_state != 1
        )
        buy_flip[i] = bf
        if bf:
            final_state = 1
        elif bool(sell_conf.iloc[i]) and (not params["avoid_repeats"] or final_state != -1):
            final_state = -1

    return pd.Series(buy_flip, index=df.index)


def merged_triple_buy_last_bar(
    df: pd.DataFrame,
    pine_code: str | None = None,
    pine_input_overrides: dict | None = None,
    **params,
) -> bool:
    if pine_code:
        params = {**merged_params_from_script(pine_code, pine_input_overrides), **params}
    series = merged_triple_buy_series(df, **params)
    if series.empty:
        return False
    return bool(series.iloc[-1]) if pd.notna(series.iloc[-1]) else False


def merged_triple_display_label(pine_code: str) -> str:
    p = merged_params_from_script(pine_code)
    return (
        "Merged-Triple BUY (plotshape buyFlip) — "
        f"ALMA {p['alma_len']}, ROC {p['roc_len']}, IU {p['iu_length']}, "
        f"confluence {p['confluence_window']} bar"
    )


def merged_triple_snapshot(
    df: pd.DataFrame, pine_code: str, pine_input_overrides: dict | None = None
) -> dict:
    p = merged_params_from_script(pine_code, pine_input_overrides)
    flips = merged_triple_buy_series(df, **p)
    return {
        "merged_triple_buy": bool(flips.iloc[-1]) if len(flips) else False,
        "params": p,
    }
