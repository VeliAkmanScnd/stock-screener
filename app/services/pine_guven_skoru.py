"""FX Sinyal Güven Skoru (Güven %) — last-bar BUY/SELL via buyCond/sellCond."""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from app.services import indicators as ind
from app.services.pine_params import merge_pine_inputs

GUVEN_SKORU_MARKER = "__GUVEN_SKORU_LAST__"

_XS_ADX = np.array([10.0, 15.0, 20.0, 25.0, 40.0, 60.0])
_YS_ADX = np.array([0.0, 0.15, 0.5, 0.85, 1.0, 0.6])
_XS_TR = np.array([-5.0, -1.0, 0.0, 1.0, 5.0])
_YS_TR = np.array([0.0, 0.1, 0.4, 0.8, 1.0])
_XS_MOM = np.array([-3.0, -1.0, 0.0, 1.0, 2.0, 5.0, 8.0])
_YS_MOM = np.array([0.0, 0.1, 0.3, 0.7, 1.0, 1.0, 0.6])
_XS_CCI = np.array([-200.0, -100.0, 0.0, 50.0, 100.0, 200.0, 300.0])
_YS_CCI = np.array([0.0, 0.1, 0.4, 0.8, 1.0, 0.6, 0.2])
_XS_ATR = np.array([0.5, 0.8, 1.0, 1.5, 2.0, 3.0])
_YS_ATR = np.array([0.2, 0.7, 1.0, 0.9, 0.5, 0.1])


def _parse_indicator_title(code: str) -> str:
    m = re.search(r'indicator\s*\(\s*"([^"]+)"', code, flags=re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r'shorttitle\s*=\s*"([^"]+)"', code, flags=re.I)
    return m.group(1).strip() if m else "Güven Skoru"


def is_guven_skoru_script(code: str) -> bool:
    raw = re.sub(r"//.*?$", "", code, flags=re.MULTILINE)
    has_conds = bool(re.search(r"\bbuyCond\b", raw) and re.search(r"\bsellCond\b", raw))
    has_scores = bool(re.search(r"\bf_scores\b", raw) and re.search(r"\bbTot\b", raw))
    has_title = bool(
        re.search(r"FX\s*Sinyal\s*Güven\s*Skoru|Güven\s*%", raw, flags=re.I)
        or re.search(r"Guven\s*%", raw, flags=re.I)
    )
    return (has_conds and has_scores) or (has_title and has_conds)


def _as_bool(val, default: bool) -> bool:
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    if s in ("1", "true", "yes", "on"):
        return True
    if s in ("0", "false", "no", "off"):
        return False
    return default


def _as_float(val, default: float) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _as_int(val, default: int) -> int:
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return default


def guven_params_from_script(pine_code: str, overrides: dict | None = None) -> dict:
    inputs = merge_pine_inputs(pine_code, overrides)
    return {
        "thr": _as_float(inputs.get("thr"), 80.0),
        "only_conf": _as_bool(inputs.get("onlyConf"), True),
        "adx_len": _as_int(inputs.get("adxLen"), 14),
        "mom_len": _as_int(inputs.get("momLen"), 10),
        "cci_len": _as_int(inputs.get("cciLen"), 20),
        "ema_len": _as_int(inputs.get("emaLen"), 200),
        "atr_avg_len": _as_int(inputs.get("atrAvgLen"), 50),
        "w_adx": _as_float(inputs.get("wAdx"), 25.0),
        "w_trend": _as_float(inputs.get("wTrend"), 25.0),
        "w_mom": _as_float(inputs.get("wMom"), 20.0),
        "w_cci": _as_float(inputs.get("wCci"), 15.0),
        "w_atr": _as_float(inputs.get("wAtr"), 15.0),
        "alma_len": _as_int(inputs.get("almaLen"), 24),
        "alma_off": _as_float(inputs.get("almaOff"), 0.7),
        "alma_sig": _as_float(inputs.get("almaSig"), 4.0),
        "per_len": _as_int(inputs.get("perLen"), 21),
        "med_len": _as_int(inputs.get("medLen"), 21),
        "med_mult": _as_float(inputs.get("medMult"), 1.8),
        # Always match either long or short threshold signal.
        "side": "both",
    }


def guven_display_label(pine_code: str, overrides: dict | None = None) -> str:
    p = guven_params_from_script(pine_code, overrides)
    title = _parse_indicator_title(pine_code)
    return f"Güven Skoru eşik {p['thr']:g}% — {title}"


def _ramp(x: pd.Series, xs: np.ndarray, ys: np.ndarray) -> pd.Series:
    return pd.Series(np.interp(x.to_numpy(dtype=float), xs, ys), index=x.index)


def _dmi(
    high: pd.Series, low: pd.Series, close: pd.Series, length: int
) -> tuple[pd.Series, pd.Series, pd.Series]:
    up = high.diff()
    down = -low.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=close.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=close.index)
    atr_vals = ind.atr(high, low, close, length)
    plus_di = 100 * plus_dm.ewm(alpha=1 / length, adjust=False).mean() / atr_vals
    minus_di = 100 * minus_dm.ewm(alpha=1 / length, adjust=False).mean() / atr_vals
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx_v = dx.ewm(alpha=1 / length, adjust=False).mean()
    return plus_di, minus_di, adx_v


def _scores(
    d: int,
    *,
    close: pd.Series,
    atr_v: pd.Series,
    di_p: pd.Series,
    di_m: pd.Series,
    adx_v: pd.Series,
    cci_v: pd.Series,
    ema_v: pd.Series,
    atr_rat: pd.Series,
    mom_v: pd.Series,
    w_adx: float,
    w_trend: float,
    w_mom: float,
    w_cci: float,
    w_atr: float,
) -> pd.Series:
    s_adx = _ramp(adx_v, _XS_ADX, _YS_ADX) * np.where(d * (di_p - di_m) > 0, 1.0, 0.3)
    s_tr = _ramp(d * (close - ema_v) / atr_v.replace(0, np.nan), _XS_TR, _YS_TR)
    s_mom = _ramp(d * mom_v / atr_v.replace(0, np.nan), _XS_MOM, _YS_MOM)
    s_cci = _ramp(d * cci_v, _XS_CCI, _YS_CCI)
    s_atr = _ramp(atr_rat, _XS_ATR, _YS_ATR)
    w_sum = w_adx + w_trend + w_mom + w_cci + w_atr
    if w_sum <= 0:
        w_sum = 1.0
    raw = (
        s_adx * w_adx + s_tr * w_trend + s_mom * w_mom + s_cci * w_cci + s_atr * w_atr
    ) / w_sum
    weak = (
        (s_adx < 0.3).astype(int)
        + (s_tr < 0.3).astype(int)
        + (s_mom < 0.3).astype(int)
        + (s_cci < 0.3).astype(int)
        + (s_atr < 0.3).astype(int)
    )
    return raw * 100 * np.where(weak >= 2, 0.8, 1.0)


def guven_series(df: pd.DataFrame, **params) -> dict[str, pd.Series]:
    thr = float(params.get("thr", 80.0))
    adx_len = int(params.get("adx_len", 14))
    mom_len = int(params.get("mom_len", 10))
    cci_len = int(params.get("cci_len", 20))
    ema_len = int(params.get("ema_len", 200))
    atr_avg_len = int(params.get("atr_avg_len", 50))
    alma_len = int(params.get("alma_len", 24))
    alma_off = float(params.get("alma_off", 0.7))
    alma_sig = float(params.get("alma_sig", 4.0))
    per_len = int(params.get("per_len", 21))
    med_len = int(params.get("med_len", 21))
    med_mult = float(params.get("med_mult", 1.8))

    h, l, c = df["High"], df["Low"], df["Close"]
    atr_v = ind.atr(h, l, c, adx_len)
    di_p, di_m, adx_v = _dmi(h, l, c, adx_len)
    cci_v = ind.cci(h, l, c, cci_len)
    ema_v = ind.ema(c, ema_len)
    atr_rat = atr_v / ind.sma(atr_v, atr_avg_len)
    mom_v = c - c.shift(mom_len)

    score_kw = dict(
        close=c,
        atr_v=atr_v,
        di_p=di_p,
        di_m=di_m,
        adx_v=adx_v,
        cci_v=cci_v,
        ema_v=ema_v,
        atr_rat=atr_rat,
        mom_v=mom_v,
        w_adx=float(params.get("w_adx", 25.0)),
        w_trend=float(params.get("w_trend", 25.0)),
        w_mom=float(params.get("w_mom", 20.0)),
        w_cci=float(params.get("w_cci", 15.0)),
        w_atr=float(params.get("w_atr", 15.0)),
    )
    b_tot = _scores(1, **score_kw)
    s_tot = _scores(-1, **score_kw)

    alma = ind.alma(c, alma_len, alma_off, alma_sig)
    p75 = alma.rolling(per_len).quantile(0.75)
    p25 = alma.rolling(per_len).quantile(0.25)
    median = c.rolling(med_len).median()
    med_abs = (c - median).abs()
    med_filt = med_abs.rolling(med_len).median()
    long_c = c > (p75 + med_filt * med_mult)
    short_c = c < (p25 - med_filt)

    qb = np.zeros(len(df), dtype=int)
    lc = long_c.fillna(False).to_numpy(dtype=bool)
    sc = short_c.fillna(False).to_numpy(dtype=bool)
    for i in range(len(df)):
        prev = qb[i - 1] if i else 0
        if lc[i] and not sc[i]:
            qb[i] = 1
        elif sc[i]:
            qb[i] = -1
        else:
            qb[i] = prev
    qb_s = pd.Series(qb, index=df.index)

    # Scanner uses drop_unclosed_bar → last bar is confirmed (onlyConf).
    buy_cross = (b_tot > thr) & (b_tot.shift(1).fillna(0) <= thr)
    sell_cross = (s_tot > thr) & (s_tot.shift(1).fillna(0) <= thr)
    alma_long_flip = (qb_s == 1) & (qb_s.shift(1).fillna(0) != 1)
    alma_short_flip = (qb_s == -1) & (qb_s.shift(1).fillna(0) != -1)
    buy_cond = (qb_s == 1) & (buy_cross | (alma_long_flip & (b_tot >= thr)))
    sell_cond = (qb_s == -1) & (sell_cross | (alma_short_flip & (s_tot >= thr)))

    return {
        "buy_tot": b_tot,
        "sell_tot": s_tot,
        "qb": qb_s,
        "buy_cond": buy_cond.fillna(False),
        "sell_cond": sell_cond.fillna(False),
    }


def guven_snapshot(df: pd.DataFrame, **params) -> dict:
    side = params.pop("side", "both")
    if df is None or len(df) < 30:
        return {
            "pine_al": False,
            "guven_buy": False,
            "guven_sell": False,
            "guven_side": side,
            "guven_buy_score": None,
            "guven_sell_score": None,
        }
    s = guven_series(df, **params)
    buy = bool(s["buy_cond"].iloc[-1])
    sell = bool(s["sell_cond"].iloc[-1])
    if side == "sell":
        ok = sell
    elif side == "both":
        ok = buy or sell
    else:
        ok = buy
    b_score = s["buy_tot"].iloc[-1]
    s_score = s["sell_tot"].iloc[-1]
    return {
        "pine_al": ok,
        "guven_buy": buy,
        "guven_sell": sell,
        "guven_side": side,
        "guven_buy_score": float(b_score) if pd.notna(b_score) else None,
        "guven_sell_score": float(s_score) if pd.notna(s_score) else None,
        "buy": buy,
        "sell": sell,
    }


def guven_from_script(
    df: pd.DataFrame,
    pine_code: str,
    pine_input_overrides: dict | None = None,
) -> bool:
    params = guven_params_from_script(pine_code, pine_input_overrides)
    return bool(guven_snapshot(df, **params).get("pine_al"))
