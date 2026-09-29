"""Bias x Trend Strength (CEREBR HA bias + TS bands) — last-bar BUY/SELL."""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from app.services import indicators as ind
from app.services.bar_close import TIMEFRAME_SECONDS
from app.services.pine_params import merge_pine_inputs

BIAS_TS_MARKER = "__BIAS_TS_LAST__"

PINE_TF_SECONDS: dict[str, int] = {
    **TIMEFRAME_SECONDS,
    "1": 60,
    "3": 180,
    "5": 300,
    "15": 900,
    "30": 1800,
    "45": 2700,
    "60": 3600,
    "120": 7200,
    "180": 10800,
    "240": 14400,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "d": 86400,
    "1d": 86400,
    "w": 604800,
    "1w": 604800,
}


def _parse_indicator_title(code: str) -> str:
    m = re.search(r'indicator\s*\(\s*"([^"]+)"', code, flags=re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r'shorttitle\s*=\s*"([^"]+)"', code, flags=re.I)
    return m.group(1).strip() if m else "Bias x Trend Strength"


def is_bias_ts_script(code: str) -> bool:
    raw = re.sub(r"//.*?$", "", code, flags=re.MULTILINE)
    has_sigs = bool(re.search(r"\bbuy_sig\b", raw) and re.search(r"\bts_green\b", raw))
    has_title = bool(re.search(r"Bias\s*[x×]\s*Trend\s*Strength", raw, flags=re.I))
    has_armed = bool(re.search(r"\bbuy_armed\b", raw) and re.search(r"\bts_buy\b", raw))
    return has_sigs and (has_title or has_armed)


def _as_bool(val: str | None, default: bool) -> bool:
    if val is None:
        return default
    return str(val).strip().lower() in ("1", "true", "yes", "on")


def _as_int(val: str | None, default: int) -> int:
    try:
        return int(float(val)) if val is not None and str(val).strip() else default
    except (TypeError, ValueError):
        return default


def _as_float(val: str | None, default: float) -> float:
    try:
        return float(val) if val is not None and str(val).strip() else default
    except (TypeError, ValueError):
        return default


def _tf_seconds(tf: str | None) -> int | None:
    key = str(tf or "").strip().strip('"').strip("'").lower()
    if not key:
        return None
    return PINE_TF_SECONDS.get(key)


def _hold_on_htf(series: pd.Series, ha_htf: str | None, chart_tf: str | None) -> pd.Series:
    """Pine: o2s := newHtf ? o2 : o2s[1] when ha_htf is slower than the chart."""
    htf_sec = _tf_seconds(ha_htf)
    chart_sec = _tf_seconds(chart_tf)
    if htf_sec is None:
        return series
    if chart_sec is not None and htf_sec <= chart_sec:
        return series
    idx = series.index
    if not isinstance(idx, pd.DatetimeIndex) or len(series) == 0:
        return series
    freq = pd.Timedelta(seconds=htf_sec)
    bucket_s = pd.Series(idx.floor(freq), index=idx)
    new_htf = bucket_s.ne(bucket_s.shift(1))
    new_htf.iloc[0] = True
    held = np.empty(len(series), dtype=float)
    last = np.nan
    vals = series.to_numpy(dtype=float)
    flags = new_htf.to_numpy(dtype=bool)
    for i in range(len(vals)):
        if flags[i] or not np.isfinite(last):
            last = vals[i]
        held[i] = last
    return pd.Series(held, index=idx)


def bias_ts_params_from_script(pine_code: str, overrides: dict | None = None) -> dict:
    inputs = merge_pine_inputs(pine_code, overrides)
    extra = overrides or {}
    side = str(extra.get("scan_side") or inputs.get("scan_side") or "both").strip().lower()
    if side not in ("buy", "sell", "both"):
        side = "both"
    return {
        "ha_len": max(2, _as_int(inputs.get("ha_len"), 100)),
        "ha_len2": max(2, _as_int(inputs.get("ha_len2"), 100)),
        "osc_len": max(1, _as_int(inputs.get("osc_len"), 7)),
        "lenn": max(2, _as_int(inputs.get("lenn"), 20)),
        "only_first": _as_bool(inputs.get("only_first"), True),
        "require_close_side": _as_bool(inputs.get("require_close_side"), True),
        "use_dist": _as_bool(inputs.get("use_dist"), True),
        "max_dist": max(0.0, _as_float(inputs.get("max_dist"), 5.0)),
        "ha_htf": str(inputs.get("ha_htf") or "").strip().strip('"'),
        "side": side,
    }


def bias_ts_series(
    df: pd.DataFrame,
    ha_len: int = 100,
    ha_len2: int = 100,
    osc_len: int = 7,
    lenn: int = 20,
    only_first: bool = True,
    require_close_side: bool = True,
    use_dist: bool = True,
    max_dist: float = 5.0,
    ha_htf: str = "",
    chart_tf: str | None = None,
) -> dict[str, pd.Series]:
    """Replay Pine Bias x TS state. ha_htf empty = chart TF (sample every bar)."""
    o_src = df["Open"].astype(float)
    h_src = df["High"].astype(float)
    l_src = df["Low"].astype(float)
    c_src = df["Close"].astype(float)

    o = ind.ema(o_src, ha_len)
    c = ind.ema(c_src, ha_len)
    h = ind.ema(h_src, ha_len)
    l = ind.ema(l_src, ha_len)
    haclose = (o + h + l + c) / 4.0
    xhaopen = (o + c) / 2.0

    haopen = np.empty(len(df), dtype=float)
    xo = xhaopen.to_numpy(dtype=float)
    hc = haclose.to_numpy(dtype=float)
    haopen[0] = xo[0] if np.isfinite(xo[0]) else np.nan
    for i in range(1, len(df)):
        prev_x = xo[i - 1]
        prev_c = hc[i - 1]
        if np.isfinite(prev_x) and np.isfinite(prev_c):
            haopen[i] = (prev_x + prev_c) / 2.0
        else:
            haopen[i] = xo[i]
    haopen_s = pd.Series(haopen, index=df.index)

    hahigh = pd.concat([h, haopen_s, haclose], axis=1).max(axis=1)
    halow = pd.concat([l, haopen_s, haclose], axis=1).min(axis=1)
    o2 = ind.ema(haopen_s, ha_len2)
    c2 = ind.ema(haclose, ha_len2)
    h2 = ind.ema(hahigh, ha_len2)
    l2 = ind.ema(halow, ha_len2)
    o2s = _hold_on_htf(o2, ha_htf, chart_tf)
    c2s = _hold_on_htf(c2, ha_htf, chart_tf)
    h2s = _hold_on_htf(h2, ha_htf, chart_tf)
    l2s = _hold_on_htf(l2, ha_htf, chart_tf)
    ha_avg = (h2s + l2s) / 2.0
    osc_bias = 100.0 * (c2s - o2s)

    src = c_src
    basis = ind.sma(src, lenn)
    stdev = src.rolling(lenn).std(ddof=1)
    upper = basis + stdev
    lower = basis - stdev
    ts_green = src > upper
    ts_red = src < lower
    bias_bull = osc_bias > 0
    bias_bear = osc_bias < 0
    bias_flip_bull = bias_bull & (~bias_bull.shift(1).fillna(False).astype(bool))
    bias_flip_bear = bias_bear & (~bias_bear.shift(1).fillna(False).astype(bool))

    dist = (src - ha_avg) / ha_avg.abs() * 100.0
    buy_extended = use_dist & dist.notna() & (dist > max_dist)
    sell_extended = use_dist & dist.notna() & (dist < -max_dist)
    close_above = src > ha_avg
    close_below = src < ha_avg
    buy_setup = bias_bull & (~buy_extended) & ((~pd.Series(require_close_side, index=df.index)) | close_above)
    sell_setup = bias_bear & (~sell_extended) & ((~pd.Series(require_close_side, index=df.index)) | close_below)

    n = len(df)
    buy_armed = np.zeros(n, dtype=float)
    sell_armed = np.zeros(n, dtype=float)
    fired = np.zeros(n, dtype=float)
    buy_sig = np.zeros(n, dtype=bool)
    sell_sig = np.zeros(n, dtype=bool)

    bb = bias_bull.to_numpy(dtype=bool)
    be = bias_bear.to_numpy(dtype=bool)
    tg = ts_green.fillna(False).to_numpy(dtype=bool)
    tr = ts_red.fillna(False).to_numpy(dtype=bool)
    bs = buy_setup.fillna(False).to_numpy(dtype=bool)
    ss = sell_setup.fillna(False).to_numpy(dtype=bool)
    flip_b = bias_flip_bull.fillna(False).to_numpy(dtype=bool)
    flip_s = bias_flip_bear.fillna(False).to_numpy(dtype=bool)

    for i in range(n):
        prev_ba = buy_armed[i - 1] if i else 0.0
        prev_sa = sell_armed[i - 1] if i else 0.0
        buy_armed[i] = 0.0 if not bb[i] else (1.0 if not tg[i] else prev_ba)
        sell_armed[i] = 0.0 if not be[i] else (1.0 if not tr[i] else prev_sa)

        prev_tg = tg[i - 1] if i else False
        prev_tr = tr[i - 1] if i else False
        ts_buy = buy_armed[i] == 1.0 and tg[i] and not prev_tg
        ts_sell = sell_armed[i] == 1.0 and tr[i] and not prev_tr
        cand_buy = bool(bs[i] and ts_buy)
        cand_sell = bool(ss[i] and ts_sell)

        prev_f = 0.0 if (flip_b[i] or flip_s[i]) else (fired[i - 1] if i else 0.0)
        bsig = cand_buy and (not only_first or prev_f != 1.0)
        ssig = cand_sell and (not only_first or prev_f != -1.0)
        buy_sig[i] = bsig
        sell_sig[i] = ssig
        fired[i] = 1.0 if bsig else (-1.0 if ssig else prev_f)

    idx = df.index
    return {
        "osc_bias": osc_bias,
        "ha_avg": ha_avg,
        "ts_green": ts_green.fillna(False),
        "ts_red": ts_red.fillna(False),
        "bias_bull": bias_bull.fillna(False),
        "bias_bear": bias_bear.fillna(False),
        "buy_sig": pd.Series(buy_sig, index=idx),
        "sell_sig": pd.Series(sell_sig, index=idx),
        "bias_dist_pct": dist,
    }


def bias_ts_snapshot(df: pd.DataFrame, **params) -> dict:
    side = params.pop("side", "both")
    chart_tf = params.pop("chart_tf", None)
    need = params.get("ha_len", 100) + params.get("ha_len2", 100) + params.get("lenn", 20) + 5
    if df is None or len(df) < need:
        return {
            "pine_al": False,
            "bias_ts_buy": False,
            "bias_ts_sell": False,
            "bias_ts_side": side,
        }
    s = bias_ts_series(df, chart_tf=chart_tf, **params)
    buy = bool(s["buy_sig"].iloc[-1])
    sell = bool(s["sell_sig"].iloc[-1])
    if side == "sell":
        ok = sell
    elif side == "both":
        ok = buy or sell
    else:
        ok = buy
    dist = s["bias_dist_pct"].iloc[-1]
    return {
        "pine_al": ok,
        "bias_ts_buy": buy,
        "bias_ts_sell": sell,
        "bias_ts_side": side,
        "bias_bull": bool(s["bias_bull"].iloc[-1]),
        "ts_green": bool(s["ts_green"].iloc[-1]),
        "bias_dist_pct": float(dist) if pd.notna(dist) else None,
    }


def bias_ts_from_script(
    df: pd.DataFrame, pine_code: str, pine_input_overrides: dict | None = None
) -> bool:
    params = bias_ts_params_from_script(pine_code, pine_input_overrides)
    return bool(bias_ts_snapshot(df, **params).get("pine_al"))


def bias_ts_display_label(pine_code: str, overrides: dict | None = None) -> str:
    title = _parse_indicator_title(pine_code)
    p = bias_ts_params_from_script(pine_code, overrides)
    side = {"buy": "BUY", "sell": "SELL", "both": "BUY veya SELL"}.get(p["side"], "BUY")
    return f"BiasxTS {side} (kapanan son bar) — {title}"
