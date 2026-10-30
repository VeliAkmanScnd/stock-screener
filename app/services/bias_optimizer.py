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
from collections.abc import Iterable, Iterator
from typing import Any, Callable

import pandas as pd

from app.services.bar_close import drop_unclosed_bar
from app.services.borsapy_client import BACKTEST_PERIODS, backtest_period_days, coverage_note
from app.services.pine_market_bias import (
    bias_signal_pack,
    market_bias_from_pack,
    market_bias_series,
    summarize_bias_trades,
)
from app.utils.json_safe import json_safe

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, int, int, str], None]
StopCheck = Callable[[], bool]
SnapshotCallback = Callable[[dict[str, Any]], None]


class OptimizeCancelled(Exception):
    """User asked to stop a running Bias tester job."""

MAX_COMBOS = 50000
SCAN_ALL_MAX = 10_000_000
RESULT_SLICE = 500
RESULT_LIMIT = RESULT_SLICE * 3
RANGE_AXIS_MAX = 400
REFINE_BASE_STRIDES = (4, 2, 1)
REFINE_MAX_STRIDE = 256
REFINE_TOP = 16
REFINE_MIN_RADIUS = 16
REFINE_SPACE_WIDE = 100_000
REFINE_SPACE_HUGE = 10_000_000
NUMERIC_REFINE_KEYS = (
    "ha_len",
    "ha_len2",
    "osc_len",
    "ha_htf",
    "rr_mult",
    "swing_bars",
    "tp_pct",
    "sl_pct",
    "max_same",
)
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


def combo_budget(body: dict[str, Any], space: int) -> int:
    """How many engine combos to run. scan_all enumerates the full grid."""
    if body.get("scan_all"):
        if space > SCAN_ALL_MAX:
            raise ValueError(
                f"Izgara {space} set. Tamamını tara en fazla {SCAN_ALL_MAX}. "
                "Adımı büyütün veya optimize etmediğiniz eksenleri kapatın."
            )
        return max(1, int(space))
    return max(20, min(MAX_COMBOS, int(body.get("max_combos") or MAX_COMBOS)))


_HALTON_PRIMES = (
    2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61,
)


def _halton_perm(base: int, rng: random.Random) -> list[int]:
    perm = list(range(base))
    if base > 2:
        tail = perm[1:]
        rng.shuffle(tail)
        perm = [0] + tail
    return perm


def _radical_inverse(index: int, base: int, perm: list[int]) -> float:
    value = 0.0
    f = 1.0 / base
    n = int(index)
    while n > 0:
        value += perm[n % base] * f
        n //= base
        f /= base
    return value


def _qmc_index_rows(axis_sizes: list[int], n: int, seed: int) -> list[list[int]]:
    """Scrambled Halton points mapped onto a mixed discrete grid (Sobol-like)."""
    if n <= 0:
        return []
    sizes = [max(1, int(L)) for L in axis_sizes]
    active = [j for j, L in enumerate(sizes) if L > 1]
    rng = random.Random(seed)
    primes = _HALTON_PRIMES[: max(1, len(active))]
    perms = [_halton_perm(p, rng) for p in primes]
    rows: list[list[int]] = []
    for i in range(1, n + 1):
        idxs = [0] * len(sizes)
        for k, j in enumerate(active):
            u = _radical_inverse(i, primes[k], perms[k])
            idxs[j] = min(sizes[j] - 1, int(u * sizes[j]))
        rows.append(idxs)
    return rows


def _lhs_index_rows(axis_sizes: list[int], n: int, rng: random.Random) -> list[list[int]]:
    """Latin hypercube: each axis is stratified across the n samples."""
    if n <= 0:
        return []
    sizes = [max(1, int(L)) for L in axis_sizes]
    cols: list[list[int]] = []
    for L in sizes:
        order = list(range(n))
        rng.shuffle(order)
        col = [0] * n
        for pos, rank in enumerate(order):
            u = (rank + rng.random()) / n
            col[pos] = min(L - 1, int(u * L))
        cols.append(col)
    d = len(sizes)
    return [[cols[j][i] for j in range(d)] for i in range(n)]


def expand_combos(grid: dict[str, list], max_combos: int, seed: int = 42) -> list[dict[str, Any]]:
    keys = list(ENGINE_KEYS)
    values = [list(grid.get(k) or [None]) for k in keys]
    for i, vals in enumerate(values):
        if not vals:
            values[i] = [None]
    total = 1
    for vals in values:
        total *= len(vals)
    cap = max(1, int(max_combos or 180))
    if total <= cap:
        return [dict(zip(keys, row)) for row in itertools.product(*values)]

    n_axes = len(keys)
    sizes = [len(vals) for vals in values]
    mids = [max(0, len(vals) // 2) for vals in values]
    ends = [len(vals) - 1 for vals in values]
    preferred = [_preferred_index(keys[j], values[j]) for j in range(n_axes)]
    seen: set[tuple[int, ...]] = set()
    out: list[dict[str, Any]] = []

    def add(idxs: list[int]) -> bool:
        clipped = [min(max(0, i), ends[j]) for j, i in enumerate(idxs)]
        key = tuple(clipped)
        if key in seen:
            return False
        seen.add(key)
        out.append(_combo_from_indices(keys, values, clipped))
        return True

    add([0] * n_axes)
    add(preferred)
    add(mids)
    add(ends)

    remaining = cap - len(out)
    n_active = sum(1 for L in sizes if L > 1) or 1
    # Keep axis walks, but leave most of the budget for interior QMC/LHS.
    sweep_budget = max(n_active * 4, remaining // 5)
    sweep = max(5, min(80, sweep_budget // n_active))
    for j, vals in enumerate(values):
        if len(out) >= cap:
            return out[:cap]
        last = len(vals) - 1
        steps = min(len(vals), sweep)
        for s in range(steps):
            idxs = preferred[:]
            idxs[j] = 0 if steps == 1 else round(s * last / (steps - 1))
            add(idxs)
            if len(out) >= cap:
                return out[:cap]

    need = cap - len(out)
    if need > 0:
        for row in _qmc_index_rows(sizes, need * 3 + 64, seed):
            add(row)
            if len(out) >= cap:
                return out[:cap]
        rng = random.Random(seed + 17)
        extra = 0
        while len(out) < cap and extra < 8:
            extra += 1
            batch = max(need, cap - len(out))
            for row in _lhs_index_rows(sizes, batch, rng):
                add(row)
                if len(out) >= cap:
                    return out[:cap]
        guard = 0
        while len(out) < cap and guard < cap * 40:
            guard += 1
            add([rng.randrange(L) for L in sizes])
    return out[:cap]


def iter_full_grid(grid: dict[str, list]) -> Iterator[dict[str, Any]]:
    keys = list(ENGINE_KEYS)
    values = [list(grid.get(k) or [None]) for k in keys]
    for i, vals in enumerate(values):
        if not vals:
            values[i] = [None]
    for row in itertools.product(*values):
        yield dict(zip(keys, row))


def coarsen_values(vals: list, stride: int) -> list:
    if not vals:
        return []
    stride = max(1, int(stride))
    if stride <= 1 or len(vals) <= 2:
        return list(vals)
    idxs = list(range(0, len(vals), stride))
    last = len(vals) - 1
    if idxs[-1] != last:
        idxs.append(last)
    return [vals[i] for i in idxs]


def axis_refine_stride(vals: list, stride: int) -> int:
    """Keep short axes (RR, swing, osc) dense; only HA-sized lists jump by `stride`."""
    n = len(vals)
    if n <= 8:
        return 1
    keep_min = 8
    max_stride = max(1, (n - 1) // (keep_min - 1))
    return min(max(1, int(stride)), max_stride)


def coarsen_grid(grid: dict[str, list], stride: int) -> dict[str, list]:
    out: dict[str, list] = {}
    for key in ENGINE_KEYS:
        vals = list(grid.get(key) or [None])
        if key in NUMERIC_REFINE_KEYS:
            out[key] = coarsen_values(vals, axis_refine_stride(vals, stride))
        else:
            out[key] = vals
    return out


def refine_strides(grid: dict[str, list], cap: int | None = None) -> list[int]:
    """Zoom layers after discovery. Always +1 (8), often +2 (16), huge grids +3 (32)."""
    space = grid_space(grid)
    strides = [8, 4, 2, 1]
    if space > REFINE_SPACE_WIDE:
        strides.insert(0, 16)
    if space > REFINE_SPACE_HUGE:
        strides.insert(0, 32)
    return strides


def _value_index(vals: list, value: Any) -> int:
    for i, v in enumerate(vals):
        if v == value:
            return i
        try:
            if abs(float(v) - float(value)) < 1e-9:
                return i
        except (TypeError, ValueError):
            continue
    try:
        nums = [float(x) for x in vals]
        target = float(value)
        return min(range(len(vals)), key=lambda i: abs(nums[i] - target))
    except (TypeError, ValueError):
        return 0


def neighborhood_values(
    vals: list,
    centers: list,
    prev_stride: int,
    next_stride: int,
    radius: int | None = None,
) -> list:
    if not vals:
        return []
    if not centers:
        return coarsen_values(vals, next_stride)
    prev_stride = max(1, int(prev_stride))
    next_stride = max(1, int(next_stride))
    span = max(prev_stride, int(radius) if radius is not None else prev_stride)
    lo = len(vals) - 1
    hi = 0
    center_idxs: list[int] = []
    for c in centers:
        i = _value_index(vals, c)
        center_idxs.append(i)
        lo = min(lo, max(0, i - span))
        hi = max(hi, min(len(vals) - 1, i + span))
    keep = set(center_idxs)
    start = lo - (lo % next_stride)
    for i in range(max(0, start), hi + 1, next_stride):
        if lo <= i <= hi:
            keep.add(i)
    return [vals[i] for i in sorted(keep)]


def _seed_axis_value(row: dict[str, Any], key: str) -> Any:
    params = row.get("params") if isinstance(row.get("params"), dict) else row
    aliases = {
        "rr_mult": ("rr_mult", "rrMult"),
        "swing_bars": ("swing_bars", "swingBars"),
        "exit_mode": ("exit_mode", "exitMode"),
        "max_same": ("max_same", "maxSame"),
    }
    for name in aliases.get(key, (key,)):
        if name in params and params[name] is not None:
            val = params[name]
            if key == "ha_htf":
                return str(val)
            return val
    return None


def neighborhood_grid(
    full: dict[str, list],
    seeds: list[dict[str, Any]],
    prev_stride: int,
    next_stride: int,
) -> dict[str, list]:
    out: dict[str, list] = {}
    for key in ENGINE_KEYS:
        vals = list(full.get(key) or [None])
        if key not in NUMERIC_REFINE_KEYS or len(vals) <= 1:
            out[key] = vals
            continue
        centers = []
        for seed in seeds:
            val = _seed_axis_value(seed, key)
            if val is not None:
                centers.append(val)
        out[key] = neighborhood_values(
            vals,
            centers,
            prev_stride,
            next_stride,
            radius=max(prev_stride, REFINE_MIN_RADIUS),
        )
    return out


def combos_for_grid(
    grid: dict[str, list],
    cap: int,
    seed: int = 42,
) -> tuple[list[dict[str, Any]], int, bool]:
    space = grid_space(grid)
    if space <= cap:
        return list(iter_full_grid(grid)), space, False
    listed = expand_combos(grid, cap, seed=seed)
    return listed, len(listed), True


def _merge_unique_combos(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple] = set()
    out: list[dict[str, Any]] = []
    for group in groups:
        for combo in group:
            try:
                sig = _combo_sig(combo)
            except (TypeError, ValueError, KeyError):
                out.append(combo)
                continue
            if sig in seen:
                continue
            seen.add(sig)
            out.append(combo)
    return out


def discovery_combos(
    grid: dict[str, list],
    cap: int,
    seed: int,
    coarse_stride: int,
) -> tuple[list[dict[str, Any]], bool]:
    """Fine-grid Sobol (the search that finds HA 70 / swing 9) plus a coarse lattice if it fits."""
    cap = max(1, int(cap))
    fine, _, sampled = combos_for_grid(grid, cap, seed=seed)
    coarse = coarsen_grid(grid, coarse_stride)
    coarse_space = grid_space(coarse)
    if 1 < coarse_space <= cap:
        listed = _merge_unique_combos(list(iter_full_grid(coarse)), fine)
    else:
        listed = fine
    return listed, sampled or grid_space(grid) > len(listed)


def describe_search_plan(body: dict[str, Any]) -> dict[str, Any]:
    grid = build_grid(body)
    space = grid_space(grid)
    scan_all = bool(body.get("scan_all"))
    cap = max(20, min(MAX_COMBOS, int(body.get("max_combos") or MAX_COMBOS)))
    if scan_all:
        return {
            "mode": "full",
            "tours": 1,
            "strides": [1],
            "space": space,
            "cap": cap,
            "tour1_space": space,
            "tour1_sampled": False,
            "extra_tours": 0,
        }
    if space <= cap:
        return {
            "mode": "full",
            "tours": 1,
            "strides": [1],
            "space": space,
            "cap": cap,
            "tour1_space": space,
            "tour1_sampled": False,
            "extra_tours": 0,
        }
    strides = refine_strides(grid, cap)
    coarse_space = grid_space(coarsen_grid(grid, strides[0]))
    tour1 = min(space, cap + (coarse_space if coarse_space <= cap else 0))
    return {
        "mode": "refine",
        "tours": 1 + len(strides),
        "strides": strides,
        "space": space,
        "cap": cap,
        "tour1_space": tour1,
        "tour1_sampled": True,
        "tour1_discovery": True,
        "extra_tours": max(0, len(strides) - len(REFINE_BASE_STRIDES)),
    }


def refine_combo_score(row: dict[str, Any]) -> float:
    """Kâr × WR — both need to be high; sparse high-WR / low-profit sets lose."""
    profit = _finite_num(row.get("net_profit_pct"), 0.0)
    wr = _finite_num(row.get("win_rate"), 0.0)
    if profit <= 0:
        return profit
    return profit * wr


def _seed_region(row: dict[str, Any]) -> tuple:
    ha = int(_finite_num(_seed_axis_value(row, "ha_len"), 0))
    ha2 = int(_finite_num(_seed_axis_value(row, "ha_len2"), 0))
    rr = _finite_num(_seed_axis_value(row, "rr_mult"), 0)
    swing = int(_finite_num(_seed_axis_value(row, "swing_bars"), 0))
    return (ha // 8, ha2 // 8, round(rr * 2) / 2, swing // 4)


def _take_unique_regions(
    rows: list[dict[str, Any]],
    n: int,
    seen: set[tuple],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        if len(out) >= n:
            break
        region = _seed_region(row)
        if region in seen:
            continue
        seen.add(region)
        out.append(row)
    return out


def pick_refine_seeds(found: dict[str, Any], n: int = REFINE_TOP) -> list[dict[str, Any]]:
    """Two groups: highest-profit regions and highest-WR regions, then fill by kâr×WR."""
    n = max(2, int(n))
    rows = [r for r in (found.get("results") or []) if r.get("tag") != "referans"]
    if not rows:
        return []
    profit_rows = sorted(
        rows,
        key=lambda r: (
            not r.get("passed"),
            -_finite_num(r.get("net_profit_pct"), 0.0),
            -_finite_num(r.get("trades"), 0.0),
            -_finite_num(r.get("win_rate"), 0.0),
        ),
    )
    wr_rows = sorted(
        rows,
        key=lambda r: (
            not r.get("passed"),
            -_finite_num(r.get("win_rate"), 0.0),
            -_finite_num(r.get("net_profit_pct"), 0.0),
        ),
    )
    combo_rows = sorted(
        rows,
        key=lambda r: (
            not r.get("passed"),
            -refine_combo_score(r),
            -_finite_num(r.get("net_profit_pct"), 0.0),
            -_finite_num(r.get("win_rate"), 0.0),
        ),
    )
    n_profit = (n + 1) // 2
    n_wr = n - n_profit
    seen: set[tuple] = set()
    picked = _take_unique_regions(profit_rows, n_profit, seen)
    picked.extend(_take_unique_regions(wr_rows, n_wr, seen))
    if len(picked) < n:
        picked.extend(_take_unique_regions(combo_rows, n - len(picked), seen))
    return picked


def _strip_rank(row: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if k != "rank"}


def _assemble_found(
    *,
    tested: int,
    passed: int,
    errors: int,
    first_error: str,
    cancelled: bool,
    partial: bool,
    refs: list[dict[str, Any]],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    ranked = _ranked_results([_strip_rank(r) for r in refs], [_strip_rank(r) for r in rows])
    return {
        "tested": tested,
        "passed": passed,
        "errors": errors,
        "error": first_error or None,
        "cancelled": cancelled,
        "partial": partial,
        "reference": next((r for r in ranked if r.get("tag") == "referans"), None),
        "best": _pick_best(ranked),
        "results": ranked,
    }


def _with_reference(
    combos: Iterable[dict[str, Any]],
    reference: dict[str, Any] | None,
) -> Iterator[dict[str, Any]]:
    if not reference:
        yield from combos
        return
    sig = _combo_sig(reference)
    yield reference
    for combo in combos:
        try:
            if _combo_sig(combo) == sig:
                continue
        except (TypeError, ValueError, KeyError):
            pass
        yield combo


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


def engine_from_public(params: dict[str, Any]) -> dict[str, Any]:
    raw = dict(params or {})
    aliases = {
        "exitMode": "exit_mode",
        "rrMult": "rr_mult",
        "swingBars": "swing_bars",
        "maxSame": "max_same",
    }
    for src, dst in aliases.items():
        if src in raw and (dst not in raw or raw.get(dst) in (None, "")):
            raw[dst] = raw[src]
    return _engine_typed(raw)


def _month_key(iso: str) -> str:
    try:
        return pd.Timestamp(iso).strftime("%Y-%m")
    except (TypeError, ValueError):
        text = str(iso or "")
        return text[:7] if len(text) >= 7 else text


def build_strategy_chart(
    trades: list[dict[str, Any]] | None,
    start_equity: float = 10000.0,
) -> dict[str, Any]:
    closed = [t for t in (trades or []) if t.get("reason")]
    equity = float(start_equity)
    peak = equity
    first_t = ""
    if closed:
        first_t = str(closed[0].get("entry_time") or closed[0].get("exit_time") or "")
    points: list[dict[str, Any]] = [
        {"t": first_t, "equity": round(equity, 2), "pnl_pct": 0.0, "dd_pct": 0.0, "side": "", "reason": ""}
    ]
    month_pnl: dict[str, float] = {}
    for trade in closed:
        pnl = float(trade.get("pnl_pct") or 0.0)
        delta = equity * pnl / 100.0
        equity *= 1.0 + pnl / 100.0
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak * 100.0 if peak else 0.0
        exit_t = str(trade.get("exit_time") or "")
        points.append(
            {
                "t": exit_t,
                "equity": round(equity, 2),
                "pnl_pct": round(pnl, 4),
                "dd_pct": round(dd, 2),
                "side": str(trade.get("side") or ""),
                "reason": str(trade.get("reason") or ""),
            }
        )
        key = _month_key(exit_t)
        if key:
            month_pnl[key] = month_pnl.get(key, 0.0) + delta
    months = [{"period": key, "pnl": round(val, 2)} for key, val in sorted(month_pnl.items())]
    return {
        "start_equity": round(float(start_equity), 2),
        "end_equity": round(equity, 2),
        "equity": points,
        "months": months,
    }


def chart_from_frame(
    df,
    *,
    chart_tf: str,
    params: dict[str, Any],
    start_equity: float = 10000.0,
) -> dict[str, Any]:
    frame = prepare_backtest_ohlcv(df)
    if frame is None or frame.empty:
        raise RuntimeError("OHLCV hazırlanamadı")
    engine = engine_from_public(params)
    series = market_bias_series(frame, chart_tf=chart_tf, **engine)
    trades = list(series.get("trades") or [])
    metrics = _sanitize_metrics(summarize_bias_trades(trades, start_equity=start_equity))
    curve = build_strategy_chart(trades, start_equity=start_equity)
    start = frame.index[0]
    end = frame.index[-1]
    return json_safe(
        {
            "timeframe": chart_tf,
            "bars": int(len(frame)),
            "from": start.isoformat() if hasattr(start, "isoformat") else str(start),
            "to": end.isoformat() if hasattr(end, "isoformat") else str(end),
            "params": _public_params(engine),
            "metrics": metrics,
            "trades": trades,
            **curve,
        }
    )


def load_backtest_frame(symbol: str, timeframe: str, period: str):
    from app.services.borsapy_client import fetch_ohlcv_one_backtest

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
    return df


def get_job_frame(job_id: str):
    with _lock:
        job = _jobs.get(job_id)
        return None if not job else job.frame


def chart_bias_combo(body: dict[str, Any]) -> dict[str, Any]:
    from app.services.borsapy_client import is_borsapy_available, tradingview_auth_configured

    symbol = str(body.get("symbol") or "").strip().upper()
    timeframe = str(body.get("timeframe") or "15m").strip()
    period = str(body.get("period") or "60d").strip() or "60d"
    if period not in BACKTEST_PERIODS:
        raise ValueError("Veri süresi 40 gün–2 yıl aralığında olmalı")
    if not symbol:
        raise ValueError("Sembol gerekli")
    if timeframe not in ("3m", "5m", "15m", "30m", "1h", "1d"):
        raise ValueError("Periyot 3m, 5m, 15m, 30m, 1h veya 1d olmalı")
    params = body.get("params") if isinstance(body.get("params"), dict) else {}
    start_equity = float(body.get("start_equity") or 10000.0)
    job_id = str(body.get("job_id") or "").strip()
    df = get_job_frame(job_id) if job_id else None
    if df is None:
        if not is_borsapy_available():
            raise RuntimeError("borsapy yüklü değil")
        if not tradingview_auth_configured():
            raise RuntimeError("TradingView sessionid / sessionid_sign .env içinde yok")
        df = load_backtest_frame(symbol, timeframe, period)
    out = chart_from_frame(df, chart_tf=timeframe, params=params, start_equity=start_equity)
    out["symbol"] = symbol
    out["period"] = period
    return out


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
    if hours >= 36:
        days = hours / 24.0
        whole_d = int(days)
        rem_h = int(round(hours - whole_d * 24))
        if rem_h <= 0:
            return f"{max(1, whole_d)} gün"
        return f"{whole_d} gün {rem_h} sa"
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


def _result_rank_key(row: dict[str, Any]) -> tuple:
    return (
        not row.get("passed"),
        -_finite_num(row.get("profit_factor"), 0.0),
        -_finite_num(row.get("net_profit_pct"), 0.0),
        -_finite_num(row.get("win_rate"), 0.0),
        _finite_num(row.get("max_drawdown"), 0.0),
    )


def _profit_keep_key(row: dict[str, Any]) -> tuple:
    return (
        not row.get("passed"),
        -_finite_num(row.get("net_profit_pct"), 0.0),
        -_finite_num(row.get("trades"), 0.0),
        -_finite_num(row.get("win_rate"), 0.0),
    )


def _wr_keep_key(row: dict[str, Any]) -> tuple:
    return (
        not row.get("passed"),
        -_finite_num(row.get("win_rate"), 0.0),
        -_finite_num(row.get("net_profit_pct"), 0.0),
        -_finite_num(row.get("trades"), 0.0),
    )


def _row_identity(row: dict[str, Any]) -> tuple:
    params = row.get("params") if isinstance(row.get("params"), dict) else {}
    if params:
        return tuple(sorted((str(k), str(v)) for k, v in params.items()))
    return (id(row),)


def _keep_diverse_rows(rows: list[dict[str, Any]], limit: int = RESULT_LIMIT) -> list[dict[str, Any]]:
    """Keep 500 kâr + 500 WR + 500 PF (or limit/3 each in tests)."""
    slice_n = RESULT_SLICE if limit >= RESULT_SLICE * 3 else max(1, int(limit) // 3)
    cap = slice_n * 3
    if len(rows) <= cap:
        return list(rows)
    n_profit = slice_n
    n_wr = slice_n
    n_pf = slice_n
    seen: set[tuple] = set()
    out: list[dict[str, Any]] = []

    def take(sorted_rows: list[dict[str, Any]], count: int) -> None:
        added = 0
        for row in sorted_rows:
            if added >= count:
                return
            ident = _row_identity(row)
            if ident in seen:
                continue
            seen.add(ident)
            out.append(row)
            added += 1

    take(sorted(rows, key=_profit_keep_key), n_profit)
    take(sorted(rows, key=_wr_keep_key), n_wr)
    take(sorted(rows, key=_result_rank_key), n_pf)
    return out


def _pick_best(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    cand = [r for r in rows if r.get("passed") and r.get("tag") != "referans"]
    if not cand:
        cand = [r for r in rows if r.get("tag") != "referans"]
    if not cand:
        return None
    return max(
        cand,
        key=lambda r: (
            _finite_num(r.get("net_profit_pct"), 0.0),
            _finite_num(r.get("win_rate"), 0.0),
            _finite_num(r.get("trades"), 0.0),
        ),
    )


def _progress_step(total: int) -> int:
    if total <= 80:
        return 1
    if total <= 2000:
        return 2
    if total <= 50000:
        return 8
    return max(20, min(500, total // 400))


def _ranked_results(refs: list[dict[str, Any]], buf: list[dict[str, Any]]) -> list[dict[str, Any]]:
    kept = _keep_diverse_rows(buf, RESULT_LIMIT)
    rest = sorted(
        kept,
        key=lambda r: (
            not r.get("passed"),
            -_finite_num(r.get("net_profit_pct"), 0.0),
            -_finite_num(r.get("win_rate"), 0.0),
            -_finite_num(r.get("profit_factor"), 0.0),
        ),
    )
    ranked = []
    for idx, row in enumerate(list(refs) + rest, start=1):
        ranked.append({"rank": idx, **row})
    return ranked


def _ha_sort_key(params: dict[str, Any]) -> tuple:
    try:
        return (
            int(params.get("ha_len") or 0),
            int(params.get("ha_len2") or 0),
            int(params.get("osc_len") or 0),
            str(params.get("ha_htf") or ""),
        )
    except (TypeError, ValueError):
        return (0, 0, 0, "")


def _order_combos_for_cache(combos: Iterable[dict[str, Any]]) -> Iterable[dict[str, Any]]:
    if not isinstance(combos, (list, tuple)):
        return combos
    tagged = [c for c in combos if str(c.get("_tag") or "") == "referans"]
    rest = [c for c in combos if str(c.get("_tag") or "") != "referans"]
    rest.sort(key=_ha_sort_key)
    return tagged + rest


def search_bias_params(
    df,
    *,
    chart_tf: str,
    combos: Iterable[dict[str, Any]],
    filters: dict[str, float],
    on_progress: ProgressCallback | None = None,
    grid_size: int | None = None,
    total: int | None = None,
    should_stop: StopCheck | None = None,
    on_snapshot: SnapshotCallback | None = None,
) -> dict[str, Any]:
    frame = prepare_backtest_ohlcv(df)
    if frame is None or frame.empty:
        raise RuntimeError("OHLCV hazırlanamadı")
    ordered = _order_combos_for_cache(combos)
    try:
        planned = int(total) if total is not None else len(ordered)  # type: ignore[arg-type]
    except TypeError:
        planned = 0
    refs: list[dict[str, Any]] = []
    buf: list[dict[str, Any]] = []
    passed_n = 0
    errors = 0
    first_error = ""
    attempted = 0
    cancelled = False
    started = time.monotonic()
    last_snap = 0.0
    step = _progress_step(planned)
    pack = None
    pack_key: tuple | None = None
    swing_cache: dict[int, tuple] = {}

    def trim_buf() -> None:
        if len(buf) <= RESULT_LIMIT:
            return
        kept = _keep_diverse_rows(buf, RESULT_LIMIT)
        buf.clear()
        buf.extend(kept)

    def emit_snapshot() -> None:
        nonlocal last_snap
        if not on_snapshot:
            return
        last_snap = time.monotonic()
        ranked = _ranked_results(refs, buf)
        on_snapshot(
            {
                "tested": attempted,
                "passed": passed_n,
                "errors": errors,
                "error": first_error or None,
                "cancelled": cancelled,
                "partial": True,
                "reference": next((r for r in ranked if r.get("tag") == "referans"), None),
                "best": _pick_best(ranked),
                "results": ranked,
            }
        )

    for i, params in enumerate(ordered, start=1):
        if should_stop and should_stop():
            cancelled = True
            break
        attempted = i
        passed = False
        try:
            engine = _engine_typed(params)
            key = (
                engine["ha_len"],
                engine["ha_len2"],
                engine["osc_len"],
                engine["ha_htf"],
                chart_tf,
            )
            if pack is None or key != pack_key:
                pack = bias_signal_pack(
                    frame,
                    ha_len=engine["ha_len"],
                    ha_len2=engine["ha_len2"],
                    osc_len=engine["osc_len"],
                    ha_htf=engine["ha_htf"],
                    chart_tf=chart_tf,
                )
                pack_key = key
            series = market_bias_from_pack(pack, swing_cache=swing_cache, **engine)
            metrics = _sanitize_metrics(summarize_bias_trades(series.get("trades")))
            passed = combo_passes(metrics, filters)
            row = {
                **metrics,
                "passed": bool(passed),
                "tag": str(params.get("_tag") or ""),
                "params": _public_params(engine),
            }
            if row["tag"] == "referans":
                refs.append(row)
            else:
                buf.append(row)
                if len(buf) > RESULT_LIMIT * 4:
                    trim_buf()
            if passed:
                passed_n += 1
        except Exception as exc:
            errors += 1
            if not first_error:
                first_error = f"{type(exc).__name__}: {exc}"
            logger.warning("bias combo failed %s: %s", params, exc)
        denom = planned or attempted
        tick = i == denom or i <= 3 or i % step == 0
        now = time.monotonic()
        if on_progress and tick:
            elapsed = now - started
            pct = 100.0 * i / denom if denom else 0.0
            eta = ""
            if i < denom and i >= 2 and elapsed >= 1.0:
                eta = format_eta(elapsed * (denom - i) / i)
            on_progress(
                "searching",
                i,
                denom,
                _search_progress_label(i, denom, grid_size, pct=pct, eta=eta),
            )
        if on_snapshot and (tick or (passed and now - last_snap >= 0.4) or now - last_snap >= 0.8):
            emit_snapshot()
    trim_buf()
    if not refs and not buf:
        if cancelled:
            return {
                "tested": attempted,
                "passed": 0,
                "errors": errors,
                "error": first_error or None,
                "cancelled": True,
                "partial": False,
                "reference": None,
                "best": None,
                "results": [],
            }
        raise RuntimeError(
            f"Hiçbir kombinasyon hesaplanamadı ({errors}/{attempted}): {first_error or 'bilinmeyen hata'}"
        )
    ranked = _ranked_results(refs, buf)
    reference = next((r for r in ranked if r.get("tag") == "referans"), None)
    best = _pick_best(ranked)
    return {
        "tested": attempted,
        "passed": passed_n,
        "errors": errors,
        "error": first_error or None,
        "cancelled": cancelled,
        "partial": False,
        "reference": reference,
        "best": best,
        "results": ranked,
    }


def run_bias_optimize(
    body: dict[str, Any],
    on_progress: ProgressCallback | None = None,
    should_stop: StopCheck | None = None,
    on_partial: SnapshotCallback | None = None,
    on_frame: Callable[[Any], None] | None = None,
) -> dict[str, Any]:
    from app.services.borsapy_client import (
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

    def stopped() -> bool:
        return bool(should_stop and should_stop())

    if stopped():
        raise OptimizeCancelled("Tarama durduruldu")

    grid = build_grid(body)
    space = grid_space(grid)
    max_combos = combo_budget(body, space)
    plan = describe_search_plan(body)
    seed = int(body.get("seed") or 42)
    sampling = str(plan.get("mode") or "full")

    if on_progress:
        on_progress("downloading", 0, 1, f"{symbol} {timeframe} indiriliyor")
    if stopped():
        raise OptimizeCancelled("Tarama durduruldu")
    df = load_backtest_frame(symbol, timeframe, period)
    if on_frame:
        on_frame(df)
    if stopped():
        raise OptimizeCancelled("Tarama durduruldu")

    reference = parse_reference(body)
    filters = {
        "min_win_rate": float(body.get("min_win_rate") or 0),
        "max_drawdown": float(body.get("max_drawdown") if body.get("max_drawdown") is not None else 100),
        "min_profit_factor": float(body.get("min_profit_factor") or 0),
        "min_profit": float(body.get("min_profit") or 0),
        "min_trades": float(body.get("min_trades") or 8),
    }
    start = df.index[0]
    end = df.index[-1]
    tour_stats: list[dict[str, Any]] = []
    meta = {
        "symbol": symbol,
        "timeframe": timeframe,
        "period": period,
        "bars": int(len(df)),
        "from": start.isoformat() if hasattr(start, "isoformat") else str(start),
        "to": end.isoformat() if hasattr(end, "isoformat") else str(end),
        "filters": filters,
        "grid_size": space,
        "sampling": sampling,
        "refine": plan,
        "coverage_note": coverage_note(timeframe, period, (end - start).days if hasattr(end - start, "days") else 0),
    }

    acc_tested = 0
    acc_passed = 0
    acc_errors = 0
    acc_error = ""
    acc_refs: list[dict[str, Any]] = []
    acc_rows: list[dict[str, Any]] = []
    seen_sigs: set[tuple] = set()
    cancelled = False
    planned_total = max(1, int(plan.get("tours") or 1)) * 1000

    def snapshot_acc(*, partial: bool, cancelled_flag: bool = False) -> dict[str, Any]:
        return _assemble_found(
            tested=acc_tested,
            passed=acc_passed,
            errors=acc_errors,
            first_error=acc_error,
            cancelled=cancelled_flag,
            partial=partial,
            refs=acc_refs,
            rows=acc_rows,
        )

    def emit_partial(found: dict[str, Any]) -> None:
        if not on_partial:
            return
        on_partial({**meta, "combo_count": int(found.get("tested") or acc_tested), "tour_stats": tour_stats, **found})

    def run_one_pass(
        combos: Iterable[dict[str, Any]],
        planned: int,
        grid_size: int,
        progress_cb: ProgressCallback | None,
    ) -> dict[str, Any]:
        prev_tested = acc_tested
        prev_passed = acc_passed
        prev_errors = acc_errors
        prev_rows = list(acc_rows)
        prev_refs = list(acc_refs)

        def on_snap(snap: dict[str, Any]) -> None:
            live_rows = prev_rows + [r for r in (snap.get("results") or []) if r.get("tag") != "referans"]
            live_refs = list(prev_refs)
            if snap.get("reference"):
                live_refs = [snap["reference"]]
            emit_partial(
                _assemble_found(
                    tested=prev_tested + int(snap.get("tested") or 0),
                    passed=prev_passed + int(snap.get("passed") or 0),
                    errors=prev_errors + int(snap.get("errors") or 0),
                    first_error=acc_error or str(snap.get("error") or ""),
                    cancelled=bool(snap.get("cancelled")),
                    partial=True,
                    refs=live_refs,
                    rows=live_rows,
                )
            )

        return search_bias_params(
            df,
            chart_tf=timeframe,
            combos=combos,
            filters=filters,
            on_progress=progress_cb,
            grid_size=grid_size,
            total=planned,
            should_stop=should_stop,
            on_snapshot=on_snap if on_partial else None,
        )

    def absorb(found: dict[str, Any]) -> None:
        nonlocal acc_tested, acc_passed, acc_errors, acc_error, cancelled
        acc_tested += int(found.get("tested") or 0)
        acc_passed += int(found.get("passed") or 0)
        acc_errors += int(found.get("errors") or 0)
        if not acc_error and found.get("error"):
            acc_error = str(found.get("error"))
        cancelled = bool(cancelled or found.get("cancelled"))
        if found.get("reference") and not acc_refs:
            acc_refs.append(found["reference"])
        acc_rows.extend(r for r in (found.get("results") or []) if r.get("tag") != "referans")

    if sampling != "refine":
        combos: Iterable[dict[str, Any]] = iter_full_grid(grid)
        planned = space
        if reference:
            combos = _with_reference(combos, reference)
            planned += 1
        if on_progress:
            on_progress("searching", 0, planned, _search_progress_label(0, planned, space, pct=0))
        found = run_one_pass(combos, planned, space, on_progress)
        absorb(found)
    else:
        zoom_strides = [int(s) for s in (plan.get("strides") or [8, 4, 2, 1])]
        n_tours = 1 + max(1, len(zoom_strides))
        current_grid = grid
        acc_state = {"results": []}
        tour_jobs: list[tuple[str, int, int]] = [("discovery", zoom_strides[0], 0)]
        for zi, zstride in enumerate(zoom_strides):
            prev = zoom_strides[zi - 1] if zi else zoom_strides[0]
            tour_jobs.append(("zoom", zstride, prev))
        for t, (kind, stride, prev_stride) in enumerate(tour_jobs):
            if stopped():
                cancelled = True
                break
            if kind == "discovery":
                listed, sampled = discovery_combos(grid, max_combos, seed, stride)
                planned = len(listed)
                current_grid = grid
            else:
                seeds = pick_refine_seeds(acc_state)
                if not seeds:
                    break
                current_grid = neighborhood_grid(grid, seeds, prev_stride, stride)
                listed, planned, sampled = combos_for_grid(current_grid, max_combos, seed=seed + t)
            fresh: list[dict[str, Any]] = []
            for combo in listed:
                try:
                    sig = _combo_sig(combo)
                except (TypeError, ValueError, KeyError):
                    fresh.append(combo)
                    continue
                if sig in seen_sigs:
                    continue
                seen_sigs.add(sig)
                fresh.append(combo)
            if t == 0 and reference:
                fresh = list(_with_reference(fresh, reference))
                planned = len(fresh)
            if not fresh:
                tour_stats.append(
                    {"tour": t + 1, "stride": stride, "space": grid_space(current_grid), "tested": 0, "sampled": sampled}
                )
                continue
            tour_space = grid_space(current_grid)

            def tour_progress(
                phase: str,
                done: int,
                total: int,
                detail: str = "",
                *,
                tour_i: int = t,
                tour_stride: int = stride,
                tour_sampled: bool = sampled,
                tour_grid: int = tour_space,
                tour_n: int = n_tours,
            ) -> None:
                if not on_progress:
                    return
                weight = 1000
                overall_done = tour_i * weight + int(weight * done / max(1, total))
                if tour_i == 0:
                    kind = "keşif Sobol + kaba ızgara" if tour_sampled else "keşif"
                else:
                    kind = f"her {tour_stride}. değer"
                    if tour_sampled:
                        kind += " · Sobol"
                msg = (
                    f"Tur {tour_i + 1}/{tour_n} ({kind}) · "
                    f"{detail or _search_progress_label(done, total, tour_grid)}"
                )
                on_progress(phase, overall_done, tour_n * weight, msg)

            if on_progress:
                tour_progress("searching", 0, max(1, len(fresh)), f"0/{len(fresh)}")
            found = run_one_pass(fresh, len(fresh), tour_space, tour_progress)
            absorb(found)
            acc_state = snapshot_acc(partial=True, cancelled_flag=cancelled)
            tour_stats.append(
                {
                    "tour": t + 1,
                    "stride": stride,
                    "space": tour_space,
                    "tested": int(found.get("tested") or 0),
                    "sampled": sampled,
                }
            )
            emit_partial(acc_state)
            if cancelled:
                break
        planned_total = n_tours * 1000
        found = snapshot_acc(partial=False, cancelled_flag=cancelled)

    final = snapshot_acc(partial=False, cancelled_flag=cancelled)
    if on_progress:
        if final.get("cancelled"):
            on_progress("cancelled", acc_tested, max(acc_tested, 1), "Durduruldu")
        else:
            on_progress("done", planned_total, planned_total, "Tamamlandı")
    return json_safe({
        "symbol": symbol,
        "timeframe": timeframe,
        "period": period,
        "bars": int(len(df)),
        "from": start.isoformat() if hasattr(start, "isoformat") else str(start),
        "to": end.isoformat() if hasattr(end, "isoformat") else str(end),
        "filters": filters,
        "combo_count": acc_tested,
        "grid_size": space,
        "sampling": sampling,
        "refine": {**plan, "tour_stats": tour_stats},
        "coverage_note": coverage_note(timeframe, period, (end - start).days if hasattr(end - start, "days") else 0),
        **final,
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
    cancel_requested: bool = False
    frame: Any = None
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


def optimize_job_is_running() -> bool:
    with _lock:
        return any(j.status == "running" for j in _jobs.values())


def cancel_optimize_job(job_id: str) -> dict[str, Any] | None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return None
        if job.status == "running":
            job.cancel_requested = True
            job.phase = "cancelling"
            job.message = "Durduruluyor…"
        return job_to_dict(job)


def start_optimize_job(body: dict[str, Any]) -> str:
    grid = build_grid(body)
    combo_budget(body, grid_space(grid))
    from app.services.optimize_review import review_is_running

    if review_is_running():
        raise RuntimeError("Haftalık alarm revizyonu çalışıyor; bitince veya durdurunca tekil tarama başlatın")
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

    def should_stop() -> bool:
        with _lock:
            job = _jobs.get(job_id)
            return bool(job and job.cancel_requested)

    def report(phase: str, done: int, total: int, detail: str = "") -> None:
        if should_stop() and phase not in ("cancelled", "done"):
            phase = "cancelling"
            detail = detail or "Durduruluyor…"
        if total <= 0:
            pct = 5 if phase == "downloading" else 0
        elif phase == "downloading":
            pct = 8
        elif phase in ("searching", "cancelling", "cancelled"):
            pct = int(min(100, max(0, done / total * 100))) if total else 0
        else:
            pct = 100
        _update(progress=pct, phase=phase, message=detail or phase)

    def worker() -> None:
        try:
            def on_partial(snapshot: dict[str, Any]) -> None:
                _update(result=json_safe(snapshot))

            def on_frame(frame: Any) -> None:
                _update(frame=frame)

            result = json_safe(
                run_bias_optimize(
                    body,
                    on_progress=report,
                    should_stop=should_stop,
                    on_partial=on_partial,
                    on_frame=on_frame,
                )
            )
            if result.get("cancelled") or should_stop():
                result["cancelled"] = True
                _update(
                    status="cancelled",
                    phase="cancelled",
                    message="Durduruldu",
                    result=result,
                )
            else:
                _update(status="done", progress=100, phase="done", message="Tamamlandı", result=result)
        except OptimizeCancelled:
            _update(status="cancelled", phase="cancelled", message="Durduruldu")
        except Exception as exc:
            logger.exception("bias optimize failed")
            _update(status="error", phase="error", message=str(exc), error=str(exc))

    threading.Thread(target=worker, name=f"bias-opt-{job_id[:8]}", daemon=True).start()
    return job_id
