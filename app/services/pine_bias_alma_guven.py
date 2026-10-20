"""Bias × ALMA × Güven confluence — last-bar BUY/SELL.

SELL: Bias red, close below Bias, ALMA red, Güven sell score crosses threshold
      (or ALMA flips short while score already ≥ thr). Light/dark red is the same.
BUY:  mirrored (Bias green, close above, ALMA green, Güven buy threshold).
"""

from __future__ import annotations

import re

import pandas as pd

from app.services.pine_bias_ts import (
    bias_ts_params_from_script,
    bias_ts_series,
    hold_one_bar_signal,
)
from app.services.pine_guven_skoru import guven_params_from_script, guven_series
from app.services.pine_params import merge_pine_inputs

BIAS_ALMA_GUVEN_MARKER = "__BIAS_ALMA_GUVEN_LAST__"


def _parse_indicator_title(code: str) -> str:
    m = re.search(r'indicator\s*\(\s*"([^"]+)"', code, flags=re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r'shorttitle\s*=\s*"([^"]+)"', code, flags=re.I)
    return m.group(1).strip() if m else "Bias × ALMA × Güven"


def is_bias_alma_guven_script(code: str) -> bool:
    raw = re.sub(r"//.*?$", "", code, flags=re.MULTILINE)
    if re.search(r"\bbag_buy\b", raw) and re.search(r"\bbag_sell\b", raw):
        return True
    if re.search(r"Bias\s*[x×]\s*ALMA\s*[x×]\s*G[uü]ven", raw, flags=re.I):
        return True
    if BIAS_ALMA_GUVEN_MARKER in code:
        return True
    return False


def bag_params_from_script(pine_code: str, overrides: dict | None = None) -> dict:
    bias = bias_ts_params_from_script(pine_code, overrides)
    guven = guven_params_from_script(pine_code, overrides)
    inputs = merge_pine_inputs(pine_code, overrides)
    extra = overrides or {}
    side = str(extra.get("scan_side") or inputs.get("scan_side") or bias.get("side") or "both")
    side = side.strip().lower()
    if side not in ("buy", "sell", "both"):
        side = "both"
    # Confluence always wants close on the Bias side; distance is optional.
    return {
        "ha_len": bias["ha_len"],
        "ha_len2": bias["ha_len2"],
        "osc_len": bias["osc_len"],
        "lenn": bias["lenn"],
        "ha_htf": bias["ha_htf"],
        "require_close_side": True,
        "use_dist": bias["use_dist"],
        "max_dist": bias["max_dist"],
        "thr": guven["thr"],
        "adx_len": guven["adx_len"],
        "mom_len": guven["mom_len"],
        "cci_len": guven["cci_len"],
        "ema_len": guven["ema_len"],
        "atr_avg_len": guven["atr_avg_len"],
        "w_adx": guven["w_adx"],
        "w_trend": guven["w_trend"],
        "w_mom": guven["w_mom"],
        "w_cci": guven["w_cci"],
        "w_atr": guven["w_atr"],
        "alma_len": guven["alma_len"],
        "alma_off": guven["alma_off"],
        "alma_sig": guven["alma_sig"],
        "per_len": guven["per_len"],
        "med_len": guven["med_len"],
        "med_mult": guven["med_mult"],
        "side": side,
    }


def bag_display_label(pine_code: str, overrides: dict | None = None) -> str:
    p = bag_params_from_script(pine_code, overrides)
    title = _parse_indicator_title(pine_code)
    return (
        f"Bias×ALMA×Güven eşik {p['thr']:g}% "
        f"(Bias HTF {p['ha_htf'] or 'chart'}) — {title}"
    )


def bag_series(df: pd.DataFrame, chart_tf: str | None = None, **params) -> dict[str, pd.Series]:
    bias_kw = {
        "ha_len": int(params.get("ha_len", 233)),
        "ha_len2": int(params.get("ha_len2", 233)),
        "osc_len": int(params.get("osc_len", 7)),
        "lenn": int(params.get("lenn", 60)),
        "only_first": True,
        "require_close_side": True,
        "use_dist": bool(params.get("use_dist", True)),
        "max_dist": float(params.get("max_dist", 5.0)),
        "ha_htf": str(params.get("ha_htf") or ""),
        "chart_tf": chart_tf,
    }
    guven_kw = {
        k: params[k]
        for k in (
            "thr",
            "adx_len",
            "mom_len",
            "cci_len",
            "ema_len",
            "atr_avg_len",
            "w_adx",
            "w_trend",
            "w_mom",
            "w_cci",
            "w_atr",
            "alma_len",
            "alma_off",
            "alma_sig",
            "per_len",
            "med_len",
            "med_mult",
        )
        if k in params
    }
    b = bias_ts_series(df, **bias_kw)
    g = guven_series(df, **guven_kw)
    close = df["Close"].astype(float)
    ha_avg = b["ha_avg"]
    # Bias red/green only (shade does not matter). ALMA red/green is inside buy/sell_cond.
    sell_ok = b["bias_bear"] & (close < ha_avg)
    buy_ok = b["bias_bull"] & (close > ha_avg)
    if bias_kw["use_dist"]:
        max_dist = float(bias_kw["max_dist"])
        dist = (close - ha_avg) / ha_avg.abs() * 100.0
        sell_ok = sell_ok & ~(dist.notna() & (dist < -max_dist))
        buy_ok = buy_ok & ~(dist.notna() & (dist > max_dist))
    buy_sig = (g["buy_cond"] & buy_ok).fillna(False)
    sell_sig = (g["sell_cond"] & sell_ok).fillna(False)
    return {
        "buy_sig": buy_sig,
        "sell_sig": sell_sig,
        "bias_bull": b["bias_bull"],
        "bias_bear": b["bias_bear"],
        "ha_avg": ha_avg,
        "qb": g["qb"],
        "buy_tot": g["buy_tot"],
        "sell_tot": g["sell_tot"],
        "guven_buy_cond": g["buy_cond"],
        "guven_sell_cond": g["sell_cond"],
    }


def bag_snapshot(df: pd.DataFrame, **params) -> dict:
    side = params.pop("side", "both")
    chart_tf = params.pop("chart_tf", None)
    need = (
        int(params.get("ha_len", 233))
        + int(params.get("ha_len2", 233))
        + int(params.get("lenn", 60))
        + 5
    )
    if df is None or len(df) < max(need, 30):
        return {
            "pine_al": False,
            "bag_buy": False,
            "bag_sell": False,
            "bag_side": side,
            "guven_buy_score": None,
            "guven_sell_score": None,
            "bag_bar_shift": 0,
            "buy": False,
            "sell": False,
        }
    s = bag_series(df, chart_tf=chart_tf, **params)
    # Event bars only (chart vertical lines). Do not re-fire morning marks all day.
    buy = bool(s["buy_sig"].iloc[-1])
    sell = bool(s["sell_sig"].iloc[-1])
    prev_buy = bool(s["buy_sig"].iloc[-2]) if len(s["buy_sig"]) >= 2 else False
    prev_sell = bool(s["sell_sig"].iloc[-2]) if len(s["sell_sig"]) >= 2 else False
    buy, sell, shift = hold_one_bar_signal(buy, sell, prev_buy, prev_sell, side)
    if side == "sell":
        ok = sell
    elif side == "both":
        ok = buy or sell
    else:
        ok = buy
    at = -1 - shift
    b_score = s["buy_tot"].iloc[at]
    s_score = s["sell_tot"].iloc[at]
    return {
        "pine_al": ok,
        "bag_buy": buy,
        "bag_sell": sell,
        "bag_side": side,
        "bias_bull": bool(s["bias_bull"].iloc[at]),
        "bias_bear": bool(s["bias_bear"].iloc[at]),
        "guven_buy_score": float(b_score) if pd.notna(b_score) else None,
        "guven_sell_score": float(s_score) if pd.notna(s_score) else None,
        "bag_bar_shift": shift,
        "buy": buy,
        "sell": sell,
    }


def bag_from_script(
    df: pd.DataFrame, pine_code: str, pine_input_overrides: dict | None = None
) -> bool:
    params = bag_params_from_script(pine_code, pine_input_overrides)
    return bool(bag_snapshot(df, **params).get("pine_al"))
