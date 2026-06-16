"""Evaluate a subset of Pine expressions against OHLCV + indicators."""

from __future__ import annotations

import ast
import operator
import re

import numpy as np
import pandas as pd

from app.services import indicators as ind


class PineEvalError(Exception):
    pass


# Safe AST operators for boolean/numeric expressions
_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.Gt: operator.gt,
    ast.Lt: operator.lt,
    ast.GtE: operator.ge,
    ast.LtE: operator.le,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.And: lambda a, b: a & b,
    ast.Or: lambda a, b: a | b,
    ast.Not: operator.invert,
}


def _series_env(df: pd.DataFrame) -> dict[str, pd.Series]:
    """Build evaluation namespace from dataframe columns and TA helpers."""
    c, h, l, o, v = df["Close"], df["High"], df["Low"], df["Open"], df["Volume"]
    env: dict[str, pd.Series] = {
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "volume": v,
        "hl2": (h + l) / 2,
        "hlc3": (h + l + c) / 3,
        "ohlc4": (o + h + l + c) / 4,
    }

    for col in df.columns:
        key = col.lower()
        env[key] = df[col]
        if key.startswith("ema_"):
            env[f"ema{key.split('_')[1]}"] = df[col]

    def _wrap(fn, *args, **kwargs):
        def caller(*a, **kw):
            return fn(*a, **kw)

        return caller

    env.update(
        {
            "ema": lambda src, length: ind.ema(_resolve(env, src), int(length)),
            "sma": lambda src, length: ind.sma(_resolve(env, src), int(length)),
            "rsi": lambda src, length=14: ind.rsi(_resolve(env, src), int(length)),
            "cci": lambda src, length=20: ind.cci(h, l, _resolve(env, src), int(length)),
            "atr": lambda length=14: ind.atr(h, l, c, int(length)),
            "adx": lambda length=14: ind.adx(h, l, c, int(length)),
            "mom": lambda src, length=10: ind.momentum(_resolve(env, src), int(length)),
            "alma": lambda src, length=9, offset=0.85, sigma=6: ind.alma(
                _resolve(env, src), int(length), float(offset), float(sigma)
            ),
            "crossover": lambda a, b: ind.crossover(_resolve(env, a), _resolve(env, b)),
            "crossunder": lambda a, b: ind.crossunder(_resolve(env, a), _resolve(env, b)),
            "cross": lambda a, b: ind.crossover(_resolve(env, a), _resolve(env, b)),
            "wma": lambda src, length: ind.wma(_resolve(env, src), int(length)),
            "highest": lambda src, length: ind.highest(_resolve(env, src), int(length)),
            "lowest": lambda src, length: ind.lowest(_resolve(env, src), int(length)),
        }
    )
    return env


def _first_bar_true(series: pd.Series) -> bool:
    if len(series) < 2:
        v = series.iloc[-1]
        return bool(v) if pd.notna(v) else False
    cur = bool(series.iloc[-1]) if pd.notna(series.iloc[-1]) else False
    prev = bool(series.iloc[-2]) if pd.notna(series.iloc[-2]) else False
    return cur and not prev


def _resolve(env: dict, x) -> pd.Series:
    if isinstance(x, pd.Series):
        return x
    if isinstance(x, str):
        key = x.strip().lower()
        if key in env:
            return env[key]
        raise PineEvalError(f"Unknown series: {x}")
    if isinstance(x, (int, float)):
        # broadcast scalar — use close length
        base = env["close"]
        return pd.Series(float(x), index=base.index)
    return x


def _preprocess_condition(expr: str) -> str:
    """Convert Pine-isms to Python-parseable expression."""
    e = expr.strip()
    e = re.sub(r"\bta\.(\w+)\b", r"\1", e)
    e = re.sub(r"\bmath\.(\w+)\b", r"\1", e)
    e = re.sub(r"\bstrategy\.(\w+)\b", r"\1", e)
    e = re.sub(r"\bcolor\.\w+\b", "True", e)
    e = re.sub(r"\blocation\.\w+\b", "True", e)
    e = re.sub(r"\bshape\.\w+\b", "True", e)
    e = re.sub(r"\bsize\.\w+\b", "True", e)
    e = re.sub(r"\bna\b", "None", e)
    e = re.sub(r"\band\b", " and ", e, flags=re.I)
    e = re.sub(r"\bor\b", " or ", e, flags=re.I)
    e = re.sub(r"\bnot\b", " not ", e, flags=re.I)
    # Pine: close > ema(close, 20) — keep as function calls; use eval via AST custom
    return e


def evaluate_condition(
    df: pd.DataFrame,
    condition: str,
    first_bar_only: bool = False,
) -> bool:
    """
    Return True if the condition is true on the latest bar.
    If first_bar_only, require transition (false on prior bar, true now).
    """
    if not condition or not condition.strip():
        raise PineEvalError("Empty condition")

    env = _series_env(df)
    expr = _preprocess_condition(condition)

    # Simple variable reference (e.g. "al" or "buySignal")
    if re.fullmatch(r"\w+", expr.strip()):
        key = expr.strip().lower()
        if key in env:
            series = env[key]
            if first_bar_only:
                return _first_bar_true(series.astype(bool))
            val = series.iloc[-1]
            return bool(val) if pd.notna(val) else False
        raise PineEvalError(f"Variable '{expr}' not found in data")

    try:
        result = _eval_pine_expr(expr, env)
    except Exception as exc:
        raise PineEvalError(str(exc)) from exc

    if isinstance(result, pd.Series):
        if first_bar_only:
            return _first_bar_true(result.astype(bool))
        last = result.iloc[-1]
        return bool(last) if pd.notna(last) else False
    if first_bar_only:
        return bool(result)
    return bool(result)


def evaluate_pine_al(
    df: pd.DataFrame,
    condition: str,
    source: str | None = None,
    pine_code: str | None = None,
    pine_input_overrides: dict | None = None,
) -> bool:
    """Evaluate buy signal; Fibo candle scripts always use dedicated engine."""
    from app.services.pine_fibo import FIBO_MARKER, fibo_first_green_from_script
    from app.services.pine_merged_triple import MERGED_TRIPLE_MARKER, merged_triple_buy_last_bar
    from app.services.pine_parser import _inline_variables
    from app.services.pine_params import merge_pine_inputs

    if source == "merged_triple" or condition == MERGED_TRIPLE_MARKER:
        if not pine_code:
            raise PineEvalError("Merged-Triple script dosyası gerekli")
        return merged_triple_buy_last_bar(df, pine_code, pine_input_overrides)
    if source == "candle_green_first" or condition == FIBO_MARKER:
        if not pine_code:
            raise PineEvalError("Pine script dosyası gerekli (yeşil mum indikatörü)")
        return fibo_first_green_from_script(df, pine_code, pine_input_overrides)
    expr = condition
    if pine_code and pine_input_overrides:
        inputs = merge_pine_inputs(pine_code, pine_input_overrides)
        expr = _inline_variables(pine_code, condition, inputs=inputs)
    return evaluate_condition(df, expr, first_bar_only=False)


def _eval_pine_expr(expr: str, env: dict) -> pd.Series | bool | float:
    """Evaluate expression with function calls (ema, crossover, etc.)."""

    # Handle function calls via regex substitution to known Python
    def replace_calls(s: str) -> str:
        # crossover(a,b) -> __crossover__(a,b)
        for fn in (
            "ema", "sma", "rsi", "cci", "atr", "adx", "mom", "alma",
            "crossover", "crossunder", "cross", "wma", "highest", "lowest",
        ):
            s = re.sub(rf"\b{fn}\s*\(", f"__{fn}__(", s)
        return s

    expr = replace_calls(expr)

    # Build callable wrappers in env
    local = dict(env)
    for fn in (
        "ema", "sma", "rsi", "cci", "atr", "adx", "mom", "alma",
        "crossover", "crossunder", "cross", "wma", "highest", "lowest",
    ):
        local[f"__{fn}__"] = env[fn]

    # Parse comparisons and logic by evaluating sub-expressions
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        # Fallback: line-based eval for simple comparisons
        return _eval_simple(expr, local)

    return _eval_ast(tree.body, local)


def _eval_simple(expr: str, env: dict) -> pd.Series:
    """Fallback for expressions like close > ema(close,20)."""
    # Replace identifiers
    tokens = re.findall(r"\w+\([^)]*\)|\w+|[<>=!]+|\d+\.?\d*", expr)
    parts: list = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if re.match(r"\w+\(", t):
            fn = t.split("(")[0]
            inner = t[t.index("(") + 1 : -1]
            args = [a.strip() for a in inner.split(",") if a.strip()]
            if fn in env:
                resolved = [env.get(a.lower(), env.get(a, float(a))) if a.replace(".", "").isdigit() else env.get(a.lower(), env[a.lower()]) for a in args]
                if fn == "ema":
                    parts.append(env["ema"](resolved[0], int(float(args[1]))))
                elif fn == "crossover":
                    parts.append(env["crossover"](resolved[0], resolved[1]))
                else:
                    parts.append(env[fn](*resolved))
            i += 1
            continue
        parts.append(t)
        i += 1
    raise PineEvalError(f"Could not parse: {expr}")


def _eval_ast(node, env: dict):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        key = node.id.lower()
        if key in env:
            return env[key]
        raise PineEvalError(f"Unknown name: {node.id}")
    if isinstance(node, ast.Call):
        fn_name = node.func.id if isinstance(node.func, ast.Name) else None
        if fn_name and fn_name.startswith("__") and fn_name.endswith("__"):
            fn_key = fn_name.strip("_")
            args = [_eval_ast(a, env) for a in node.args]
            return env[fn_key](*args)
        if fn_name and fn_name in env:
            args = [_eval_ast(a, env) for a in node.args]
            return env[fn_name](*args)
        raise PineEvalError(f"Unsupported call: {fn_name}")
    if isinstance(node, ast.BinOp):
        left, right = _eval_ast(node.left, env), _eval_ast(node.right, env)
        op = _OPS[type(node.op)]
        if isinstance(left, pd.Series) or isinstance(right, pd.Series):
            return op(_to_series(left, env), _to_series(right, env))
        return op(left, right)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval_ast(node.operand, env)
    if isinstance(node, ast.Compare):
        left = _eval_ast(node.left, env)
        for op, comp in zip(node.ops, node.comparators):
            right = _eval_ast(comp, env)
            l, r = _to_series(left, env), _to_series(right, env)
            if isinstance(op, ast.Gt):
                left = l > r
            elif isinstance(op, ast.Lt):
                left = l < r
            elif isinstance(op, ast.GtE):
                left = l >= r
            elif isinstance(op, ast.LtE):
                left = l <= r
            elif isinstance(op, ast.Eq):
                left = l == r
            elif isinstance(op, ast.NotEq):
                left = l != r
            else:
                raise PineEvalError("Unsupported comparison")
        return left
    if isinstance(node, ast.BoolOp):
        values = [_eval_ast(v, env) for v in node.values]
        series = [_to_series(v, env) for v in values]
        if isinstance(node.op, ast.And):
            out = series[0]
            for s in series[1:]:
                out = out & s
            return out
        out = series[0]
        for s in series[1:]:
            out = out | s
        return out
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        v = _to_series(_eval_ast(node.operand, env), env)
        return ~v.astype(bool)
    raise PineEvalError(f"Unsupported AST node: {type(node).__name__}")


def _to_series(x, env: dict) -> pd.Series:
    if isinstance(x, pd.Series):
        return x
    if isinstance(x, (int, float, bool, np.bool_)):
        base = env["close"]
        return pd.Series(x, index=base.index)
    return x
