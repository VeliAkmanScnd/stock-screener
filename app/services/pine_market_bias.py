"""Market Bias Strategy (CEREBR) — last-bar longGo / shortGo."""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from app.services import indicators as ind
from app.services.pine_bias_ts import (
    _as_bool,
    _as_float,
    _as_int,
    _tf_seconds,
)
from app.services.pine_params import merge_pine_inputs

MARKET_BIAS_MARKER = "__MARKET_BIAS_LAST__"


def _parse_indicator_title(code: str) -> str:
    for pat in (
        r"strategy\s*\(\s*(?:title\s*=\s*)?[\"']([^\"']+)",
        r"indicator\s*\(\s*(?:title\s*=\s*)?[\"']([^\"']+)",
        r"shorttitle\s*=\s*[\"']([^\"']+)",
    ):
        m = re.search(pat, code, flags=re.I)
        if m:
            return m.group(1).strip()
    return "Market Bias Strategy"


def is_market_bias_script(code: str) -> bool:
    raw = re.sub(r"//.*?$", "", code, flags=re.MULTILINE)
    if MARKET_BIAS_MARKER in code:
        return True
    has_go = bool(re.search(r"\blongGo\b", raw) and re.search(r"\bshortGo\b", raw))
    has_strength = bool(
        re.search(r"\bbuyStrength\b", raw) and re.search(r"\bsellStrength\b", raw)
    )
    has_title = bool(re.search(r"Market\s+Bias", raw, flags=re.I))
    return has_go and (has_strength or has_title)


def _force_ctf(ha_htf: str, chart_tf: str | None) -> str:
    """Pine FORCE_CTF: drop an HTF faster than the chart."""
    htf = str(ha_htf or "").strip().strip('"').strip("'")
    h_sec = _tf_seconds(htf)
    c_sec = _tf_seconds(chart_tf)
    if h_sec is None:
        return ""
    if c_sec is not None and h_sec < c_sec:
        return ""
    return htf


def market_bias_params_from_script(pine_code: str, overrides: dict | None = None) -> dict:
    inputs = merge_pine_inputs(pine_code, overrides)
    extra = overrides or {}
    side = str(extra.get("scan_side") or inputs.get("scan_side") or "both").strip().lower()
    if side not in ("buy", "sell", "both"):
        side = "both"
    exit_mode = str(inputs.get("exitMode") or "Percent").strip().strip("'").strip('"')
    return {
        "ha_len": max(2, _as_int(inputs.get("ha_len"), 100)),
        "ha_len2": max(2, _as_int(inputs.get("ha_len2"), 100)),
        "osc_len": max(1, _as_int(inputs.get("osc_len"), 7)),
        "ha_htf": str(inputs.get("ha_htf") or "").strip().strip('"').strip("'"),
        "exit_mode": exit_mode,
        "rr_mult": max(0.0, _as_float(inputs.get("rrMult"), 1.0)),
        "swing_bars": max(1, _as_int(inputs.get("swingBars"), 4)),
        "tp_pct": max(0.0, _as_float(inputs.get("tp_pct"), 2.0)),
        "sl_pct": max(0.0, _as_float(inputs.get("sl_pct"), 1.0)),
        "allow_long": _as_bool(inputs.get("allow_long"), True),
        "allow_short": _as_bool(inputs.get("allow_short"), True),
        "reverse_exit": _as_bool(inputs.get("reverse_exit"), True),
        "require_bar": _as_bool(inputs.get("require_bar"), True),
        "max_same": max(1, _as_int(inputs.get("maxSame"), 2)),
        "side": side,
    }


def _no_repaint_request(series: pd.Series, ha_htf: str, chart_tf: str | None) -> pd.Series:
    """Pine f_no_repaint_request on a slower HTF.

    Take the last chart value of each *completed* HTF bar (no lookahead into
    the open 30m while the first 15m is still printing), then delay one chart
    bar — ``request.security(..., expr)[1]`` on historical bars.
    """
    h_sec = _tf_seconds(ha_htf)
    c_sec = _tf_seconds(chart_tf)
    if h_sec is None or (c_sec is not None and h_sec <= c_sec):
        return series
    idx = series.index
    if not isinstance(idx, pd.DatetimeIndex) or len(series) == 0:
        return series
    freq = pd.Timedelta(seconds=h_sec)
    try:
        floored = idx.floor(freq)
    except Exception:
        minutes = max(1, int(h_sec // 60))
        try:
            floored = idx.floor(f"{minutes}min")
        except Exception:
            return series
    bucket = pd.Series(floored, index=idx)
    vals = series.to_numpy(dtype=float)
    flags = bucket.ne(bucket.shift(1)).to_numpy(dtype=bool)
    flags[0] = True
    n = len(vals)
    out = np.full(n, np.nan)
    bucket_last = np.nan
    finalized = np.nan
    for i in range(n):
        if flags[i] and i:
            finalized = bucket_last
        if np.isfinite(vals[i]):
            bucket_last = vals[i]
        out[i] = finalized
    return pd.Series(out, index=idx).shift(1)


def _confirmed_swings(low: pd.Series, high: pd.Series, swing: int) -> tuple[np.ndarray, np.ndarray]:
    n = len(low)
    last_low = np.full(n, np.nan)
    last_high = np.full(n, np.nan)
    ll = np.nan
    lh = np.nan
    lo = low.to_numpy(dtype=float)
    hi = high.to_numpy(dtype=float)
    for i in range(n):
        if i >= 2 * swing:
            mid = i - swing
            left = mid - swing
            window_l = lo[left : i + 1]
            window_h = hi[left : i + 1]
            if np.isfinite(lo[mid]) and lo[mid] == np.nanmin(window_l):
                ll = lo[mid]
            if np.isfinite(hi[mid]) and hi[mid] == np.nanmax(window_h):
                lh = hi[mid]
        last_low[i] = ll
        last_high[i] = lh
    return last_low, last_high


def market_bias_series(
    df: pd.DataFrame,
    ha_len: int = 100,
    ha_len2: int = 100,
    osc_len: int = 7,
    ha_htf: str = "",
    chart_tf: str | None = None,
    exit_mode: str = "Percent",
    swing_bars: int = 4,
    allow_long: bool = True,
    allow_short: bool = True,
    reverse_exit: bool = True,
    require_bar: bool = True,
    max_same: int = 2,
    rr_mult: float = 1.0,
    tp_pct: float = 2.0,
    sl_pct: float = 1.0,
    **_ignored,
) -> dict[str, pd.Series]:
    o_src = df["Open"].astype(float)
    h_src = df["High"].astype(float)
    l_src = df["Low"].astype(float)
    c_src = df["Close"].astype(float)

    o = ind.ema(o_src, ha_len)
    c = ind.ema(c_src, ha_len)
    h = ind.ema(h_src, ha_len)
    l = ind.ema(l_src, ha_len)
    held_htf = _force_ctf(ha_htf, chart_tf)
    haclose = _no_repaint_request((o + h + l + c) / 4.0, held_htf, chart_tf)
    xhaopen = _no_repaint_request((o + c) / 2.0, held_htf, chart_tf)
    mid_oc = ((o + c) / 2.0).to_numpy(dtype=float)

    haopen = np.empty(len(df), dtype=float)
    xo = xhaopen.to_numpy(dtype=float)
    hc = haclose.to_numpy(dtype=float)
    haopen[0] = mid_oc[0] if np.isfinite(mid_oc[0]) else np.nan
    for i in range(1, len(df)):
        prev_x = xo[i - 1]
        prev_c = hc[i - 1]
        if np.isfinite(prev_x) and np.isfinite(prev_c):
            haopen[i] = (prev_x + prev_c) / 2.0
        else:
            haopen[i] = mid_oc[i]
    haopen_s = pd.Series(haopen, index=df.index)
    o2 = _no_repaint_request(ind.ema(haopen_s, ha_len2), held_htf, chart_tf)
    c2 = _no_repaint_request(ind.ema(haclose, ha_len2), held_htf, chart_tf)
    osc_bias = 100.0 * (c2 - o2)
    osc_smooth = ind.ema(osc_bias, osc_len)

    strong_bull = (osc_bias > 0) & (osc_bias >= osc_smooth)
    weak_bull = (osc_bias > 0) & (osc_bias < osc_smooth)
    strong_bear = (osc_bias < 0) & (osc_bias <= osc_smooth)
    weak_bear = (osc_bias < 0) & (osc_bias > osc_smooth)
    bullish_now = osc_bias > 0
    bearish_now = osc_bias < 0
    buy_switch = bullish_now & bearish_now.shift(1, fill_value=False)
    buy_strength = strong_bull & weak_bull.shift(1, fill_value=False)
    buy_signal = buy_switch | buy_strength
    sell_switch = bearish_now & bullish_now.shift(1, fill_value=False)
    sell_strength = strong_bear & weak_bear.shift(1, fill_value=False)
    sell_signal = sell_switch | sell_strength

    bull_bar = c_src > o_src
    bear_bar = c_src < o_src
    use_swing = str(exit_mode).strip().lower() in ("swing rr", "swing_rr")
    swing_low, swing_high = _confirmed_swings(l_src, h_src, max(1, int(swing_bars)))

    n = len(df)
    idx = df.index
    long_go = np.zeros(n, dtype=bool)
    short_go = np.zeros(n, dtype=bool)
    veto_long = False
    veto_short = False
    long_streak = 0
    short_streak = 0
    pos = 0
    entry = np.nan
    stop = np.nan
    target = np.nan
    entry_i = -1
    trades: list[dict] = []
    bs = buy_signal.to_numpy(dtype=bool)
    ss = sell_signal.to_numpy(dtype=bool)
    bsw = buy_switch.to_numpy(dtype=bool)
    ssw = sell_switch.to_numpy(dtype=bool)
    bull_n = bullish_now.to_numpy(dtype=bool)
    bear_n = bearish_now.to_numpy(dtype=bool)
    bull_b = bull_bar.to_numpy(dtype=bool)
    bear_b = bear_bar.to_numpy(dtype=bool)
    close = c_src.to_numpy(dtype=float)
    high = h_src.to_numpy(dtype=float)
    low = l_src.to_numpy(dtype=float)
    rr = max(0.0, float(rr_mult))
    tp = max(0.0, float(tp_pct))
    sl = max(0.0, float(sl_pct))

    def _iso(i: int) -> str:
        val = idx[i]
        try:
            return val.isoformat()
        except AttributeError:
            return str(val)

    def _close_trade(i: int, price: float, reason: str) -> None:
        nonlocal pos, entry, stop, target, entry_i
        if pos == 0 or not np.isfinite(entry) or entry == 0 or not np.isfinite(price):
            pos = 0
            entry = np.nan
            stop = np.nan
            target = np.nan
            entry_i = -1
            return
        if pos == 1:
            pnl = (price - entry) / entry * 100.0
            side = "long"
        else:
            pnl = (entry - price) / entry * 100.0
            side = "short"
        trades.append(
            {
                "side": side,
                "entry_time": _iso(entry_i if entry_i >= 0 else i),
                "exit_time": _iso(i),
                "entry": round(float(entry), 6),
                "exit": round(float(price), 6),
                "pnl_pct": round(float(pnl), 4),
                "reason": reason,
            }
        )
        pos = 0
        entry = np.nan
        stop = np.nan
        target = np.nan
        entry_i = -1

    for i in range(n):
        if pos == 1 and np.isfinite(stop):
            if np.isfinite(low[i]) and low[i] <= stop:
                _close_trade(i, float(stop), "stop")
            elif np.isfinite(target) and np.isfinite(high[i]) and high[i] >= target:
                _close_trade(i, float(target), "target")
        elif pos == -1 and np.isfinite(stop):
            if np.isfinite(high[i]) and high[i] >= stop:
                _close_trade(i, float(stop), "stop")
            elif np.isfinite(target) and np.isfinite(low[i]) and low[i] <= target:
                _close_trade(i, float(target), "target")
        if pos == 0:
            entry = np.nan
            stop = np.nan
            target = np.nan
            entry_i = -1

        if bear_n[i]:
            veto_long = False
        if bull_n[i]:
            veto_short = False
        if require_bar and bs[i] and not bull_b[i]:
            veto_long = True
        if require_bar and ss[i] and not bear_b[i]:
            veto_short = True
        if bsw[i] or ssw[i]:
            long_streak = 0
            short_streak = 0
        swing_long_ok = np.isfinite(swing_low[i]) and swing_low[i] < close[i]
        swing_short_ok = np.isfinite(swing_high[i]) and swing_high[i] > close[i]
        can_buy = allow_long and pos <= 0 and (pos == 0 or reverse_exit)
        can_sell = allow_short and pos >= 0 and (pos == 0 or reverse_exit)
        lg = (
            bs[i]
            and can_buy
            and long_streak < max_same
            and (not require_bar or (bull_b[i] and not veto_long))
            and (not use_swing or swing_long_ok)
        )
        sg = (
            ss[i]
            and can_sell
            and short_streak < max_same
            and (not require_bar or (bear_b[i] and not veto_short))
            and (not use_swing or swing_short_ok)
        )
        long_go[i] = bool(lg)
        short_go[i] = bool(sg)
        if lg:
            if pos == -1:
                _close_trade(i, float(close[i]), "reverse")
            pos = 1
            entry = close[i]
            entry_i = i
            long_streak += 1
            short_streak = 0
            if use_swing and np.isfinite(swing_low[i]):
                stop = float(swing_low[i])
                target = entry + (entry - stop) * rr
            else:
                stop = entry * (1 - sl / 100.0) if sl > 0 else np.nan
                target = entry * (1 + tp / 100.0) if tp > 0 else np.nan
        elif sg:
            if pos == 1:
                _close_trade(i, float(close[i]), "reverse")
            pos = -1
            entry = close[i]
            entry_i = i
            short_streak += 1
            long_streak = 0
            if use_swing and np.isfinite(swing_high[i]):
                stop = float(swing_high[i])
                target = entry - (stop - entry) * rr
            else:
                stop = entry * (1 + sl / 100.0) if sl > 0 else np.nan
                target = entry * (1 - tp / 100.0) if tp > 0 else np.nan

    if pos != 0 and n:
        _close_trade(n - 1, float(close[n - 1]), "end")

    return {
        "osc_bias": osc_bias,
        "osc_smooth": osc_smooth,
        "buy_signal": buy_signal,
        "sell_signal": sell_signal,
        "long_go": pd.Series(long_go, index=idx),
        "short_go": pd.Series(short_go, index=idx),
        "swing_low": pd.Series(swing_low, index=idx),
        "swing_high": pd.Series(swing_high, index=idx),
        "trades": trades,
    }


def summarize_bias_trades(trades: list[dict] | None, start_equity: float = 10000.0) -> dict:
    """Win rate, profit factor, net profit % and max DD from closed trades."""
    closed = [t for t in (trades or []) if t.get("reason")]
    n = len(closed)
    empty = {
        "trades": 0,
        "wins": 0,
        "losses": 0,
        "longs": 0,
        "shorts": 0,
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "net_profit": 0.0,
        "net_profit_pct": 0.0,
        "max_drawdown": 0.0,
        "avg_win": 0.0,
        "avg_loss": 0.0,
        "gross_profit": 0.0,
        "gross_loss": 0.0,
    }
    if n == 0:
        return empty
    pnls = [float(t.get("pnl_pct") or 0.0) for t in closed]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gp = float(sum(wins))
    gl = abs(float(sum(losses)))
    if gl > 0:
        pf = gp / gl
    elif gp > 0:
        pf = 99.0
    else:
        pf = 0.0
    equity = float(start_equity)
    peak = equity
    max_dd = 0.0
    for p in pnls:
        equity *= 1.0 + p / 100.0
        if equity > peak:
            peak = equity
        if peak > 0:
            dd = (peak - equity) / peak * 100.0
            if dd > max_dd:
                max_dd = dd
    net_pct = (equity / start_equity - 1.0) * 100.0 if start_equity else 0.0
    return {
        "trades": n,
        "wins": len(wins),
        "losses": len(losses),
        "longs": sum(1 for t in closed if t.get("side") == "long"),
        "shorts": sum(1 for t in closed if t.get("side") == "short"),
        "win_rate": round(100.0 * len(wins) / n, 2),
        "profit_factor": round(pf, 2),
        "net_profit": round(equity - start_equity, 2),
        "net_profit_pct": round(net_pct, 2),
        "max_drawdown": round(max_dd, 2),
        "avg_win": round(sum(wins) / len(wins), 2) if wins else 0.0,
        "avg_loss": round(sum(losses) / len(losses), 2) if losses else 0.0,
        "gross_profit": round(gp, 2),
        "gross_loss": round(gl, 2),
    }


def market_bias_snapshot(df: pd.DataFrame, **params) -> dict:
    side = params.pop("side", "both")
    chart_tf = params.pop("chart_tf", None)
    tp_pct = float(params.get("tp_pct", 2.0) or 0.0)
    sl_pct = float(params.get("sl_pct", 1.0) or 0.0)
    rr_mult = float(params.get("rr_mult", 1.0) or 0.0)
    exit_mode = str(params.get("exit_mode") or "Percent")
    need = (
        int(params.get("ha_len", 100))
        + int(params.get("ha_len2", 100))
        + int(params.get("osc_len", 7))
        + 2 * int(params.get("swing_bars", 4))
        + 5
    )
    empty = {
        "pine_al": False,
        "market_bias_buy": False,
        "market_bias_sell": False,
        "market_bias_side": side,
        "market_bias_bar_shift": 0,
        "buy": False,
        "sell": False,
    }
    if df is None or len(df) < max(need, 30):
        return empty
    s = market_bias_series(df, chart_tf=chart_tf, **params)
    buy = bool(s["long_go"].iloc[-1])
    sell = bool(s["short_go"].iloc[-1])
    if side == "sell":
        buy = False
    elif side == "buy":
        sell = False
    ok = buy or sell
    at = -1
    shift = 0
    close = float(df["Close"].iloc[at])
    out = {
        "pine_al": ok,
        "market_bias_buy": buy,
        "market_bias_sell": sell,
        "market_bias_side": side,
        "market_bias_bar_shift": shift,
        "buy": buy,
        "sell": sell,
    }
    if not ok or close != close:
        return out
    use_swing = exit_mode.strip().lower() in ("swing rr", "swing_rr")
    if use_swing:
        if buy:
            sl = float(s["swing_low"].iloc[at])
            if sl == sl and close > sl:
                out["fib_entry"] = close
                out["fib_stop"] = sl
                out["fib_target"] = close + (close - sl) * rr_mult
        elif sell:
            sl = float(s["swing_high"].iloc[at])
            if sl == sl and sl > close:
                out["fib_entry"] = close
                out["fib_stop"] = sl
                out["fib_target"] = close - (sl - close) * rr_mult
    else:
        if tp_pct > 0 or sl_pct > 0:
            out["fib_entry"] = close
            if buy:
                if tp_pct > 0:
                    out["fib_target"] = close * (1 + tp_pct / 100.0)
                if sl_pct > 0:
                    out["fib_stop"] = close * (1 - sl_pct / 100.0)
            elif sell:
                if tp_pct > 0:
                    out["fib_target"] = close * (1 - tp_pct / 100.0)
                if sl_pct > 0:
                    out["fib_stop"] = close * (1 + sl_pct / 100.0)
    return out


def market_bias_from_script(
    df: pd.DataFrame, pine_code: str, pine_input_overrides: dict | None = None
) -> bool:
    params = market_bias_params_from_script(pine_code, pine_input_overrides)
    return bool(market_bias_snapshot(df, **params).get("pine_al"))


def market_bias_display_label(pine_code: str, overrides: dict | None = None) -> str:
    title = _parse_indicator_title(pine_code)
    p = market_bias_params_from_script(pine_code, overrides)
    side = {"buy": "AL", "sell": "SAT", "both": "AL veya SAT"}.get(p["side"], "AL veya SAT")
    htf = p["ha_htf"] or "chart"
    return f"Market Bias {side} (kapanan son bar, HTF {htf}) — {title}"
