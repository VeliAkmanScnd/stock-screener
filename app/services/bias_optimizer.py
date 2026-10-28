"""Market Bias parameter search — MT5-style tester on TradingView OHLCV."""

from __future__ import annotations

import itertools
import logging
import math
import random
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Callable

import pandas as pd

from app.services.bar_close import drop_unclosed_bar
from app.services.borsapy_client import BACKTEST_PERIODS, backtest_period_days, coverage_note
from app.services.pine_market_bias import market_bias_series, summarize_bias_trades
from app.utils.json_safe import json_safe

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, int, int, str], None]

MAX_COMBOS = 5000
RESULT_LIMIT = 500
RANGE_AXIS_MAX = 400
ENGINE_KEYS = (
    "ha_len",
    "ha_len2",
    "osc_len",
    "ha_htf",
    "exit_mode",
    "rr_mult",
    "swing_bars",
    "tp_pct",
    "sl_pct",
    "allow_long",
    "allow_short",
    "reverse_exit",
    "require_bar",
    "max_same",
)

QUICK_GRID: dict[str, list] = {
    "ha_len": [48, 64, 80],
    "ha_len2": [72, 96],
    "osc_len": [7, 11],
    "ha_htf": ["30"],
    "exit_mode": ["Swing RR"],
    "rr_mult": [1.2, 1.6, 2.0],
    "swing_bars": [8, 11],
    "reverse_exit": [True],
    "require_bar": [False],
    "max_same": [1, 2],
    "tp_pct": [2.0],
    "sl_pct": [1.0],
}

FULL_GRID: dict[str, list] = {
    "ha_len": [40, 52, 64, 76, 88],
    "ha_len2": [60, 76, 92, 108],
    "osc_len": [5, 7, 9, 11],
    "ha_htf": ["15", "30"],
    "exit_mode": ["Swing RR", "Percent"],
    "rr_mult": [1.0, 1.2, 1.6, 2.0],
    "swing_bars": [6, 11, 13],
    "reverse_exit": [True, False],
    "require_bar": [False, True],
    "max_same": [1, 2, 3],
    "tp_pct": [1.5, 2.5],
    "sl_pct": [1.0, 1.5],
}


def numeric_span(
    start: Any,
    stop: Any,
    step: Any,
    *,
    integer: bool,
    limit: int = RANGE_AXIS_MAX,
) -> list:
    """Inclusive start→stop walk. 55, 200, 1 → 55…200."""
    try:
        a = Decimal(str(start))
        b = Decimal(str(stop))
        s = Decimal(str(step))
    except Exception:
        return []
    if s == 0:
        s = Decimal(1)
    if a > b:
        a, b = b, a
    s = abs(s)
    out: list = []
    x = a
    for _ in range(max(1, int(limit))):
        if integer:
            val: Any = int(x.to_integral_value(rounding=ROUND_HALF_UP))
        else:
            val = float(x)
        if not out or out[-1] != val:
            out.append(val)
        nxt = x + s
        if nxt > b + (s * Decimal("1e-9")):
            break
        x = nxt
    return out


def _values_from_spec(raw: Any, *, integer: bool, fallback: list) -> list:
    if isinstance(raw, dict):
        start = raw.get("start", raw.get("from"))
        stop = raw.get("stop", raw.get("to", raw.get("end")))
        step = raw.get("step", 1)
        if start is None or stop is None:
            return list(fallback)
        out = numeric_span(start, stop, step, integer=integer)
        return out or list(fallback)
    cast = int if integer else float
    return [cast(v) for v in _parse_number_list(raw, cast, fallback)]


def _parse_number_list(raw: Any, cast, fallback: list) -> list:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return list(fallback)
    if isinstance(raw, (list, tuple)):
        parts = list(raw)
    else:
        parts = str(raw).replace(";", ",").split(",")
    out: list = []
    seen: set = set()
    for part in parts:
        text = str(part).strip()
        if not text:
            continue
        try:
            val = cast(text)
        except (TypeError, ValueError):
            continue
        if val in seen:
            continue
        seen.add(val)
        out.append(val)
    return out or list(fallback)


def _parse_bool_list(raw: Any, fallback: list[bool]) -> list[bool]:
    if raw is None or (isinstance(raw, str) and not str(raw).strip()):
        return list(fallback)
    if isinstance(raw, bool):
        return [raw]
    if isinstance(raw, (list, tuple)):
        parts = list(raw)
    else:
        parts = str(raw).replace(";", ",").split(",")
    out: list[bool] = []
    for part in parts:
        if isinstance(part, bool):
            val = part
        else:
            text = str(part).strip().lower()
            if text in ("true", "1", "evet", "on"):
                val = True
            elif text in ("false", "0", "hayir", "hayır", "off"):
                val = False
            else:
                continue
        if val not in out:
            out.append(val)
    return out or list(fallback)


def _parse_str_list(raw: Any, fallback: list[str], allowed: set[str] | None = None) -> list[str]:
    if raw is None or (isinstance(raw, str) and not str(raw).strip()):
        return list(fallback)
    if isinstance(raw, (list, tuple)):
        parts = [str(x).strip() for x in raw]
    else:
        parts = [p.strip() for p in str(raw).replace(";", ",").split(",")]
    out: list[str] = []
    for part in parts:
        if not part:
            continue
        if allowed and part not in allowed:
            continue
        if part not in out:
            out.append(part)
    return out or list(fallback)


DEFAULT_OPTIMIZE = {
    "ha_len": True,
    "ha_len2": True,
    "osc_len": True,
    "ha_htf": True,
    "exit_mode": True,
    "rr_mult": True,
    "swing_bars": True,
    "tp_pct": True,
    "sl_pct": True,
    "max_same": True,
    "reverse_exit": False,
    "require_bar": False,
}


def optimize_flags(body: dict[str, Any] | None) -> dict[str, bool]:
    raw = (body or {}).get("optimize")
    flags = dict(DEFAULT_OPTIMIZE)
    if isinstance(raw, dict):
        for key in flags:
            if key in raw:
                flags[key] = bool(raw[key])
    return flags


def _pin_list(vals: list, fallback: list) -> list:
    if vals:
        return [vals[0]]
    return list(fallback[:1] or fallback)


def _collapse_unused_exit_params(grid: dict[str, list]) -> None:
    """Percent ignores RR/swing; Swing RR ignores TP/SL — don't multiply the grid."""
    modes = set(grid.get("exit_mode") or [])
    if modes == {"Percent"}:
        grid["rr_mult"] = [float((grid.get("rr_mult") or [1.0])[0])]
        grid["swing_bars"] = [int((grid.get("swing_bars") or [4])[0])]
    elif modes == {"Swing RR"}:
        grid["tp_pct"] = [float((grid.get("tp_pct") or [2.0])[0])]
        grid["sl_pct"] = [float((grid.get("sl_pct") or [1.0])[0])]


def build_grid(body: dict[str, Any]) -> dict[str, list]:
    mode = str(body.get("mode") or "quick").strip().lower()
    base = dict(FULL_GRID if mode == "full" else QUICK_GRID)
    flags = optimize_flags(body)
    base["ha_len"] = _values_from_spec(body.get("ha_len"), integer=True, fallback=base["ha_len"])
    base["ha_len2"] = _values_from_spec(body.get("ha_len2"), integer=True, fallback=base["ha_len2"])
    base["osc_len"] = _values_from_spec(body.get("osc_len"), integer=True, fallback=base["osc_len"])
    base["rr_mult"] = _values_from_spec(body.get("rr_mult"), integer=False, fallback=base["rr_mult"])
    base["swing_bars"] = _values_from_spec(body.get("swing_bars"), integer=True, fallback=base["swing_bars"])
    base["tp_pct"] = _values_from_spec(body.get("tp_pct"), integer=False, fallback=base["tp_pct"])
    base["sl_pct"] = _values_from_spec(body.get("sl_pct"), integer=False, fallback=base["sl_pct"])
    base["max_same"] = _values_from_spec(body.get("max_same"), integer=True, fallback=base["max_same"])
    if isinstance(body.get("ha_htf"), dict):
        base["ha_htf"] = [str(v) for v in _values_from_spec(body.get("ha_htf"), integer=True, fallback=[30])]
    else:
        base["ha_htf"] = _parse_str_list(body.get("ha_htf"), base["ha_htf"])
    base["exit_mode"] = _parse_str_list(
        body.get("exit_mode"),
        base["exit_mode"],
        allowed={"Swing RR", "Percent"},
    )
    base["reverse_exit"] = _parse_bool_list(body.get("reverse_exit"), base["reverse_exit"])
    base["require_bar"] = _parse_bool_list(body.get("require_bar"), base["require_bar"])
    if not flags["ha_len"]:
        base["ha_len"] = _pin_list(base["ha_len"], QUICK_GRID["ha_len"])
    if not flags["ha_len2"]:
        base["ha_len2"] = _pin_list(base["ha_len2"], QUICK_GRID["ha_len2"])
    if not flags["osc_len"]:
        base["osc_len"] = _pin_list(base["osc_len"], QUICK_GRID["osc_len"])
    if not flags["ha_htf"]:
        base["ha_htf"] = _pin_list(base["ha_htf"], QUICK_GRID["ha_htf"])
    if not flags["rr_mult"]:
        base["rr_mult"] = _pin_list(base["rr_mult"], QUICK_GRID["rr_mult"])
    if not flags["swing_bars"]:
        base["swing_bars"] = _pin_list(base["swing_bars"], QUICK_GRID["swing_bars"])
    if not flags["tp_pct"]:
        base["tp_pct"] = _pin_list(base["tp_pct"], QUICK_GRID["tp_pct"])
    if not flags["sl_pct"]:
        base["sl_pct"] = _pin_list(base["sl_pct"], QUICK_GRID["sl_pct"])
    if not flags["max_same"]:
        base["max_same"] = _pin_list(base["max_same"], QUICK_GRID["max_same"])
    if not flags["exit_mode"]:
        base["exit_mode"] = _pin_list(base["exit_mode"], QUICK_GRID["exit_mode"])
    if not flags["reverse_exit"]:
        base["reverse_exit"] = _pin_list(base["reverse_exit"], QUICK_GRID["reverse_exit"])
    if not flags["require_bar"]:
        base["require_bar"] = _pin_list(base["require_bar"], QUICK_GRID["require_bar"])
    _collapse_unused_exit_params(base)
    side = str(body.get("side") or "both").strip().lower()
    if side == "buy":
        base["allow_long"] = [True]
        base["allow_short"] = [False]
    elif side == "sell":
        base["allow_long"] = [False]
        base["allow_short"] = [True]
    else:
        base["allow_long"] = [True]
        base["allow_short"] = [True]
    return base


def grid_space(grid: dict[str, list]) -> int:
    total = 1
    for key in ENGINE_KEYS:
        total *= max(1, len(grid.get(key) or [None]))
        if total > 10**12:
            return total
    return total


def _combo_from_indices(keys: list[str], values: list[list], idxs: list[int]) -> dict[str, Any]:
    return {keys[i]: values[i][min(idxs[i], len(values[i]) - 1)] for i in range(len(keys))}


PREFERRED_ENGINE = {
    "ha_len": 100,
    "ha_len2": 100,
    "osc_len": 7,
    "rr_mult": 1.0,
    "swing_bars": 4,
    "max_same": 1,
}


def _preferred_index(key: str, vals: list) -> int:
    pref = PREFERRED_ENGINE.get(key)
    if pref is None or not vals:
        return 0
    for i, val in enumerate(vals):
        if val == pref:
            return i
        if isinstance(val, float) and isinstance(pref, float) and abs(val - pref) < 1e-9:
            return i
    return 0


def expand_combos(grid: dict[str, list], max_combos: int, seed: int = 42) -> list[dict[str, Any]]:
    keys = list(ENGINE_KEYS)
    values = [list(grid.get(k) or [None]) for k in keys]
    for i, vals in enumerate(values):
        if not vals:
            values[i] = [None]
    total = 1
    for vals in values:
        total *= len(vals)
    cap = max(1, min(int(max_combos or 180), MAX_COMBOS))
    if total <= cap:
        return [dict(zip(keys, row)) for row in itertools.product(*values)]

    n_axes = len(keys)
    mids = [max(0, len(vals) // 2) for vals in values]
    ends = [len(vals) - 1 for vals in values]
    preferred = [_preferred_index(keys[j], values[j]) for j in range(n_axes)]
    seen: set[tuple[int, ...]] = set()
    out: list[dict[str, Any]] = []

    def add(idxs: list[int]) -> None:
        clipped = [min(max(0, i), ends[j]) for j, i in enumerate(idxs)]
        key = tuple(clipped)
        if key in seen:
            return
        seen.add(key)
        out.append(_combo_from_indices(keys, values, clipped))

    add([0] * n_axes)
    add(preferred)
    add(mids)
    add(ends)
    sweep = max(9, min(80, cap // max(4, n_axes)))
    for j, vals in enumerate(values):
        last = len(vals) - 1
        steps = min(len(vals), sweep)
        for s in range(steps):
            idxs = preferred[:]
            idxs[j] = 0 if steps == 1 else round(s * last / (steps - 1))
            add(idxs)
            if len(out) >= cap:
                return out[:cap]
    rng = random.Random(seed)
    guard = 0
    while len(out) < cap and guard < cap * 40:
        guard += 1
        add([rng.randrange(len(vals)) for vals in values])
    return out[:cap]


def prepare_backtest_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    work = df.copy()
    work = work.rename(columns=str.title)
    work = work.loc[:, ~work.columns.duplicated()]
    for col in ("Open", "High", "Low", "Close", "Volume"):
        if col not in work.columns:
            continue
        series = work[col]
        if isinstance(series, pd.DataFrame):
            series = series.iloc[:, 0]
        work[col] = pd.to_numeric(series, errors="coerce")
    needed = [c for c in ("Open", "High", "Low", "Close") if c in work.columns]
    if len(needed) < 4:
        return work.iloc[0:0]
    work = work.dropna(subset=needed)
    if not isinstance(work.index, pd.DatetimeIndex):
        parsed = pd.to_datetime(work.index, errors="coerce")
        mask = parsed.notna()
        work = work.iloc[mask.to_numpy()].copy()
        work.index = pd.DatetimeIndex(parsed[mask])
    if getattr(work.index, "tz", None) is not None:
        work.index = work.index.tz_convert("Europe/Istanbul").tz_localize(None)
    work = work[~work.index.duplicated(keep="last")].sort_index()
    return work


def _as_bool_param(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in ("true", "1", "evet", "on"):
        return True
    if text in ("false", "0", "hayir", "hayır", "off"):
        return False
    return default


def _engine_typed(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "ha_len": int(params["ha_len"]),
        "ha_len2": int(params["ha_len2"]),
        "osc_len": int(params["osc_len"]),
        "ha_htf": str(params.get("ha_htf") or ""),
        "exit_mode": str(params.get("exit_mode") or "Percent"),
        "rr_mult": float(params.get("rr_mult") or 1.0),
        "swing_bars": int(params.get("swing_bars") or 4),
        "tp_pct": float(params.get("tp_pct") or 0.0),
        "sl_pct": float(params.get("sl_pct") or 0.0),
        "allow_long": _as_bool_param(params.get("allow_long", True), True),
        "allow_short": _as_bool_param(params.get("allow_short", True), True),
        "reverse_exit": _as_bool_param(params.get("reverse_exit", True), True),
        "require_bar": _as_bool_param(params.get("require_bar", False), False),
        "max_same": int(params.get("max_same") or 1),
    }


def _combo_sig(params: dict[str, Any]) -> tuple:
    engine = _engine_typed(params)
    return tuple(engine[k] for k in ENGINE_KEYS)


def parse_reference(body: dict[str, Any]) -> dict[str, Any] | None:
    raw = body.get("reference")
    if not isinstance(raw, dict) or raw.get("enabled") is False:
        return None
    try:
        side = str(body.get("side") or "both").strip().lower()
        allow_long = side != "sell"
        allow_short = side != "buy"
        engine = _engine_typed(
            {
                "ha_len": raw.get("ha_len"),
                "ha_len2": raw.get("ha_len2"),
                "osc_len": raw.get("osc_len"),
                "ha_htf": raw.get("ha_htf", "30"),
                "exit_mode": raw.get("exit_mode") or raw.get("exitMode") or "Swing RR",
                "rr_mult": raw.get("rr_mult", raw.get("rrMult", 1.0)),
                "swing_bars": raw.get("swing_bars", raw.get("swingBars", 4)),
                "tp_pct": raw.get("tp_pct", 2.0),
                "sl_pct": raw.get("sl_pct", 1.0),
                "allow_long": allow_long,
                "allow_short": allow_short,
                "reverse_exit": raw.get("reverse_exit", True),
                "require_bar": raw.get("require_bar", False),
                "max_same": raw.get("max_same", raw.get("maxSame", 1)),
            }
        )
    except (TypeError, ValueError):
        return None
    engine["_tag"] = "referans"
    return engine


def _finite_num(value: Any, default: float = 0.0) -> float:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(num):
        return default
    return num


def _public_params(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "ha_len": int(params["ha_len"]),
        "ha_len2": int(params["ha_len2"]),
        "osc_len": int(params["osc_len"]),
        "ha_htf": str(params.get("ha_htf") or ""),
        "exitMode": str(params.get("exit_mode") or "Percent"),
        "rrMult": float(params.get("rr_mult") or 0),
        "swingBars": int(params.get("swing_bars") or 4),
        "tp_pct": float(params.get("tp_pct") or 0),
        "sl_pct": float(params.get("sl_pct") or 0),
        "allow_long": bool(params.get("allow_long", True)),
        "allow_short": bool(params.get("allow_short", True)),
        "reverse_exit": bool(params.get("reverse_exit", True)),
        "require_bar": bool(params.get("require_bar", False)),
        "maxSame": int(params.get("max_same") or 1),
    }


def combo_passes(metrics: dict[str, Any], filters: dict[str, float]) -> bool:
    if metrics["trades"] < filters["min_trades"]:
        return False
    if metrics["win_rate"] < filters["min_win_rate"]:
        return False
    if metrics["max_drawdown"] > filters["max_drawdown"]:
        return False
    if metrics["profit_factor"] < filters["min_profit_factor"]:
        return False
    if metrics["net_profit_pct"] < filters["min_profit"]:
        return False
    return True


def _sanitize_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    out = dict(metrics or {})
    int_keys = ("trades", "wins", "losses", "longs", "shorts")
    float_keys = (
        "win_rate",
        "profit_factor",
        "net_profit",
        "net_profit_pct",
        "max_drawdown",
        "avg_win",
        "avg_loss",
        "gross_profit",
        "gross_loss",
    )
    for key in int_keys:
        out[key] = int(_finite_num(out.get(key), 0.0))
    for key in float_keys:
        out[key] = round(_finite_num(out.get(key), 0.0), 2)
    return out


def format_eta(seconds: float | None) -> str:
    if seconds is None or seconds < 0 or not math.isfinite(seconds):
        return ""
    if seconds < 5:
        return "birkaç sn"
    if seconds < 90:
        return f"{int(round(seconds))} sn"
    minutes = seconds / 60.0
    if minutes < 90:
        return f"{int(round(minutes))} dk"
    hours = minutes / 60.0
    whole = int(hours)
    mins = int(round((hours - whole) * 60))
    if whole < 10 and mins:
        return f"{whole} sa {mins} dk"
    return f"{max(1, int(round(hours)))} sa"


def _search_progress_label(
    done: int,
    total: int,
    grid_size: int | None,
    *,
    pct: float | None = None,
    eta: str = "",
) -> str:
    if grid_size and grid_size > total:
        core = f"{done}/{total} örnek"
    else:
        core = f"{done}/{total}"
    parts = [core]
    if pct is not None:
        parts.append(f"%{pct:.0f}")
    if eta:
        parts.append(f"~{eta} kaldı")
    return " · ".join(parts)


def search_bias_params(
    df,
    *,
    chart_tf: str,
    combos: list[dict[str, Any]],
    filters: dict[str, float],
    on_progress: ProgressCallback | None = None,
    grid_size: int | None = None,
) -> dict[str, Any]:
    frame = prepare_backtest_ohlcv(df)
    if frame is None or frame.empty:
        raise RuntimeError("OHLCV hazırlanamadı")
    rows: list[dict[str, Any]] = []
    total = len(combos)
    errors = 0
    first_error = ""
    started = time.monotonic()
    for i, params in enumerate(combos, start=1):
        try:
            engine = _engine_typed(params)
            series = market_bias_series(frame, chart_tf=chart_tf, **engine)
            metrics = _sanitize_metrics(summarize_bias_trades(series.get("trades")))
            passed = combo_passes(metrics, filters)
            rows.append(
                {
                    **metrics,
                    "passed": bool(passed),
                    "tag": str(params.get("_tag") or ""),
                    "params": _public_params(engine),
                }
            )
        except Exception as exc:
            errors += 1
            if not first_error:
                first_error = f"{type(exc).__name__}: {exc}"
            logger.warning("bias combo failed %s: %s", params, exc)
        if on_progress and (i == total or i <= 3 or i % 2 == 0):
            elapsed = time.monotonic() - started
            pct = 100.0 * i / total if total else 0.0
            eta = ""
            if i < total and i >= 2 and elapsed >= 1.0:
                eta = format_eta(elapsed * (total - i) / i)
            on_progress(
                "searching",
                i,
                total,
                _search_progress_label(i, total, grid_size, pct=pct, eta=eta),
            )
    if not rows:
        raise RuntimeError(
            f"Hiçbir kombinasyon hesaplanamadı ({errors}/{total}): {first_error or 'bilinmeyen hata'}"
        )
    rows.sort(
        key=lambda r: (
            not r["passed"],
            -float(r["profit_factor"]),
            -float(r["net_profit_pct"]),
            -float(r["win_rate"]),
            float(r["max_drawdown"]),
        )
    )
    passed_n = sum(1 for r in rows if r["passed"])
    refs = [r for r in rows if r.get("tag") == "referans"]
    rest = [r for r in rows if r.get("tag") != "referans"][:RESULT_LIMIT]
    ranked = []
    for idx, row in enumerate(refs + rest, start=1):
        ranked.append({"rank": idx, **row})
    reference = next((r for r in ranked if r.get("tag") == "referans"), None)
    best = next((r for r in ranked if r.get("passed") and r.get("tag") != "referans"), None)
    return {
        "tested": total,
        "passed": passed_n,
        "errors": errors,
        "error": first_error or None,
        "reference": reference,
        "best": best,
        "results": ranked,
    }


def run_bias_optimize(
    body: dict[str, Any],
    on_progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    from app.services.borsapy_client import (
        fetch_ohlcv_one_backtest,
        is_borsapy_available,
        tradingview_auth_configured,
    )

    symbol = str(body.get("symbol") or "").strip().upper()
    timeframe = str(body.get("timeframe") or "15m").strip()
    period = str(body.get("period") or "60d").strip() or "60d"
    if period not in BACKTEST_PERIODS:
        raise ValueError("Veri süresi 40 gün–2 yıl aralığında olmalı")
    if not symbol:
        raise ValueError("Sembol gerekli")
    if timeframe not in ("3m", "5m", "15m", "30m", "1h", "1d"):
        raise ValueError("Periyot 3m, 5m, 15m, 30m, 1h veya 1d olmalı")
    if not is_borsapy_available():
        raise RuntimeError("borsapy yüklü değil")
    if not tradingview_auth_configured():
        raise RuntimeError("TradingView sessionid / sessionid_sign .env içinde yok")

    if on_progress:
        on_progress("downloading", 0, 1, f"{symbol} {timeframe} indiriliyor")
    df = fetch_ohlcv_one_backtest(symbol, timeframe, period=period)
    if df is None or df.empty:
        raise RuntimeError(f"{symbol} için TradingView verisi alınamadı")
    df = drop_unclosed_bar(df, timeframe, universe="viop")
    df = prepare_backtest_ohlcv(df)
    want_days = backtest_period_days(period)
    if df is not None and not df.empty:
        cut = df.index[-1] - pd.Timedelta(days=want_days)
        sliced = df[df.index >= cut]
        if len(sliced) >= 80:
            df = sliced
    if df is None or len(df) < 80:
        raise RuntimeError(f"{symbol}: yetersiz bar ({0 if df is None else len(df)})")

    grid = build_grid(body)
    space = grid_space(grid)
    max_combos = max(20, min(MAX_COMBOS, int(body.get("max_combos") or 180)))
    combos = expand_combos(grid, max_combos, seed=int(body.get("seed") or 42))
    reference = parse_reference(body)
    if reference:
        sig = _combo_sig(reference)
        combos = [reference] + [c for c in combos if _combo_sig(c) != sig]
    filters = {
        "min_win_rate": float(body.get("min_win_rate") or 0),
        "max_drawdown": float(body.get("max_drawdown") if body.get("max_drawdown") is not None else 100),
        "min_profit_factor": float(body.get("min_profit_factor") or 0),
        "min_profit": float(body.get("min_profit") or 0),
        "min_trades": float(body.get("min_trades") or 8),
    }
    if on_progress:
        on_progress(
            "searching",
            0,
            len(combos),
            _search_progress_label(0, len(combos), space, pct=0),
        )
    found = search_bias_params(
        df,
        chart_tf=timeframe,
        combos=combos,
        filters=filters,
        on_progress=on_progress,
        grid_size=space,
    )
    start = df.index[0]
    end = df.index[-1]
    if on_progress:
        on_progress("done", found["tested"], found["tested"], "Tamamlandı")
    return json_safe({
        "symbol": symbol,
        "timeframe": timeframe,
        "period": period,
        "bars": int(len(df)),
        "from": start.isoformat() if hasattr(start, "isoformat") else str(start),
        "to": end.isoformat() if hasattr(end, "isoformat") else str(end),
        "filters": filters,
        "combo_count": len(combos),
        "grid_size": space,
        "coverage_note": coverage_note(timeframe, period, (end - start).days if hasattr(end - start, "days") else 0),
        **found,
    })


@dataclass
class OptimizeJob:
    id: str
    status: str = "running"
    progress: int = 0
    phase: str = "starting"
    message: str = "Başlatılıyor…"
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


_jobs: dict[str, OptimizeJob] = {}
_lock = threading.Lock()


def job_to_dict(job: OptimizeJob) -> dict[str, Any]:
    return {
        "job_id": job.id,
        "status": job.status,
        "progress": job.progress,
        "phase": job.phase,
        "message": job.message,
        "result": job.result,
        "error": job.error,
    }


def get_optimize_job(job_id: str) -> dict[str, Any] | None:
    with _lock:
        job = _jobs.get(job_id)
        return job_to_dict(job) if job else None


def start_optimize_job(body: dict[str, Any]) -> str:
    job_id = str(uuid.uuid4())
    with _lock:
        if any(j.status == "running" for j in _jobs.values()):
            raise RuntimeError("Bir parametre taraması zaten çalışıyor")
        _jobs[job_id] = OptimizeJob(id=job_id)
        if len(_jobs) > 20:
            oldest = sorted(_jobs.values(), key=lambda j: j.created_at)[: max(0, len(_jobs) - 20)]
            for old in oldest:
                if old.status != "running":
                    _jobs.pop(old.id, None)

    def _update(**kwargs: Any) -> None:
        with _lock:
            job = _jobs.get(job_id)
            if not job:
                return
            for key, value in kwargs.items():
                setattr(job, key, value)

    def report(phase: str, done: int, total: int, detail: str = "") -> None:
        if total <= 0:
            pct = 5 if phase == "downloading" else 0
        elif phase == "downloading":
            pct = 8
        elif phase == "searching":
            pct = int(min(100, max(0, done / total * 100))) if total else 0
        else:
            pct = 100
        _update(progress=pct, phase=phase, message=detail or phase)

    def worker() -> None:
        try:
            result = json_safe(run_bias_optimize(body, on_progress=report))
            _update(status="done", progress=100, phase="done", message="Tamamlandı", result=result)
        except Exception as exc:
            logger.exception("bias optimize failed")
            _update(status="error", phase="error", message=str(exc), error=str(exc))

    threading.Thread(target=worker, name=f"bias-opt-{job_id[:8]}", daemon=True).start()
    return job_id
