"""Extract AL (buy) condition from uploaded Pine Script."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class PineInputParam:
    name: str
    kind: str
    default: str
    label: str
    group: str = ""
    options: list[str] | None = None
    minval: float | None = None
    maxval: float | None = None
    step: float | None = None


@dataclass
class PineALSignal:
    condition: str
    source: str
    variable_name: str | None = None
    first_bar_only: bool = False
    display_condition: str | None = None


def _strip_comments(code: str) -> str:
    code = re.sub(r"//.*?$", "", code, flags=re.MULTILINE)
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.DOTALL)
    return code


def _normalize_expr(expr: str) -> str:
    expr = expr.strip().rstrip(",")
    # Pine v5 uses ta.* — normalize for evaluator
    expr = re.sub(r"\bta\.(\w+)\b", r"\1", expr)
    expr = re.sub(r"\bmath\.(\w+)\b", r"\1", expr)
    expr = re.sub(r"\band\b", "and", expr, flags=re.I)
    expr = re.sub(r"\bor\b", "or", expr, flags=re.I)
    expr = re.sub(r"\bnot\b", "not", expr, flags=re.I)
    return expr


def _input_defaults(code: str) -> dict[str, str]:
    return {p.name: p.default for p in extract_pine_inputs(code)}


def extract_pine_inputs(code: str) -> list[PineInputParam]:
    """Parse Pine input.* declarations (defaults + labels + groups)."""
    raw = _strip_comments(code)
    group_vars = {
        m.group(1): m.group(2)
        for m in re.finditer(r'^(\w+)\s*=\s*"([^"]+)"\s*$', raw, flags=re.M)
    }
    params: list[PineInputParam] = []
    seen: set[str] = set()
    pattern = re.compile(
        r"(\w+)\s*=\s*input\.(int|float|bool|string|source)\(\s*"
        r"([^,]+)\s*,\s*\"([^\"]+)\"([^)]*)\)",
        flags=re.I,
    )
    for m in pattern.finditer(raw):
        name = m.group(1)
        if name in seen:
            continue
        seen.add(name)
        tail = m.group(5) or ""
        gm = re.search(r'group\s*=\s*"([^"]+)"', tail, flags=re.I)
        if gm:
            group_name = gm.group(1)
        else:
            gvar = re.search(r"group\s*=\s*(\w+)", tail, flags=re.I)
            group_name = group_vars.get(gvar.group(1), "") if gvar else ""
        opts_m = re.search(r"options\s*=\s*\[([^\]]+)\]", tail, flags=re.I)
        options: list[str] | None = None
        if opts_m:
            options = [
                o.strip().strip('"').strip("'")
                for o in opts_m.group(1).split(",")
                if o.strip()
            ]
        min_m = re.search(r"minval\s*=\s*([\d.]+)", tail, flags=re.I)
        max_m = re.search(r"maxval\s*=\s*([\d.]+)", tail, flags=re.I)
        step_m = re.search(r"step\s*=\s*([\d.]+)", tail, flags=re.I)
        params.append(
            PineInputParam(
                name=name,
                kind=m.group(2).lower(),
                default=m.group(3).strip(),
                label=m.group(4).strip(),
                group=group_name,
                options=options,
                minval=float(min_m.group(1)) if min_m else None,
                maxval=float(max_m.group(1)) if max_m else None,
                step=float(step_m.group(1)) if step_m else None,
            )
        )
    return params


def _is_merged_triple(code: str) -> bool:
    from app.services.pine_merged_triple import is_merged_triple_script

    return is_merged_triple_script(code)


def _resolve_variable(code: str, name: str, inputs: dict[str, str] | None = None) -> str | None:
    if inputs and name in inputs:
        return inputs[name]
    m = re.search(rf"\b{re.escape(name)}\s*=\s*([^\n;]+)", code, flags=re.I)
    if m:
        return _normalize_expr(m.group(1))
    return None


def _inline_variables(code: str, expr: str, depth: int = 0, inputs: dict[str, str] | None = None) -> str:
    if depth > 20:
        return expr
    if inputs is None:
        inputs = _input_defaults(code)
    for m in re.finditer(r"\b([a-zA-Z_]\w*)\b", expr):
        name = m.group(1)
        if name.lower() in ("and", "or", "not", "true", "false", "na"):
            continue
        if name in (
            "crossover", "crossunder", "cross", "ema", "sma", "rsi", "cci", "atr", "adx", "mom", "alma",
            "wma", "highest", "lowest", "color", "scale", "input",
        ):
            continue
        if name in ("close", "open", "high", "low", "volume", "hl2", "hlc3", "ohlc4"):
            continue
        sub = _resolve_variable(code, name, inputs)
        if sub and sub != expr:
            expr = re.sub(rf"\b{re.escape(name)}\b", f"({sub})", expr)
            return _inline_variables(code, expr, depth + 1, inputs)
    return expr


def _extract_indicator_title(code: str) -> str:
    m = re.search(r'indicator\s*\(\s*"([^"]+)"', code, flags=re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r'shorttitle\s*=\s*"([^"]+)"', code, flags=re.I)
    return m.group(1).strip() if m else "Mum rengi indikatörü"


def _extract_candle_green_first(code: str) -> PineALSignal | None:
    """
    Detect candle color scripts: green branch of ternary, buy = first bar turning green.
    Evaluation uses dedicated Fibo engine (no expression inlining).
    """
    if not re.search(r"\?\s*color\.green\s*:", code, flags=re.I):
        return None

    title = _extract_indicator_title(code)
    display = f"İlk yeşil mum (yeşile geçiş) — {title}"
    from app.services.pine_fibo import FIBO_MARKER

    return PineALSignal(
        condition=FIBO_MARKER,
        source="candle_green_first",
        first_bar_only=True,
        display_condition=display,
    )


def _finalize_condition(code: str, expr: str, var_name: str | None = None) -> PineALSignal:
    if re.fullmatch(r"\w+", expr.strip()):
        resolved = _resolve_variable(code, expr.strip())
        if resolved:
            expr = resolved
    expr = _inline_variables(code, expr)
    return PineALSignal(expr, "plotshape" if not var_name else "variable", var_name)


def _extract_bias_ts(code: str) -> PineALSignal | None:
    from app.services.pine_bias_ts import BIAS_TS_MARKER, bias_ts_display_label, is_bias_ts_script

    if not is_bias_ts_script(code):
        return None
    return PineALSignal(
        condition=BIAS_TS_MARKER,
        source="bias_ts",
        variable_name="buy_sig",
        first_bar_only=False,
        display_condition=bias_ts_display_label(code),
    )


def _extract_choch_bullish(code: str) -> PineALSignal | None:
    """Market structure scripts: bullish ChoCh flip (BigBeluga-style)."""
    from app.services.pine_choch import CHOCH_BULLISH_MARKER, choch_display_label, is_choch_market_structure_script

    if not is_choch_market_structure_script(code):
        return None
    return PineALSignal(
        condition=CHOCH_BULLISH_MARKER,
        source="choch_bullish",
        first_bar_only=True,
        display_condition=choch_display_label(code),
    )


def extract_al_condition(pine_code: str) -> PineALSignal | None:
    """
    Find the boolean expression that triggers an 'AL' (buy) signal.

    Priority:
    0. Merged-Triple Confluence (dedicated engine)
    1. plotshape(..., title/text containing AL or BUY)
    2. plotchar / label with AL
    3. alertcondition(..., message/title AL)
    4. Variable named *al* / *buy* / *long* used in plotshape
    5. strategy.entry long with id AL
    """
    code = _strip_comments(pine_code)

    bias_ts = _extract_bias_ts(pine_code)
    if bias_ts:
        return bias_ts

    if _is_merged_triple(pine_code):
        from app.services.pine_merged_triple import MERGED_TRIPLE_MARKER, merged_triple_display_label

        return PineALSignal(
            condition=MERGED_TRIPLE_MARKER,
            source="merged_triple",
            variable_name="buyFlip",
            display_condition=merged_triple_display_label(pine_code),
        )

    choch = _extract_choch_bullish(code)
    if choch:
        return choch

    # plotshape(cond, ..., title="AL" or "BUY")
    for m in re.finditer(
        r"plotshape\s*\(\s*([^,]+)\s*,.*?title\s*=\s*[\"'](?:AL|BUY)[\"']",
        code,
        flags=re.I | re.DOTALL,
    ):
        raw = _normalize_expr(m.group(1))
        sig = _finalize_condition(code, raw)
        sig.display_condition = sig.display_condition or "plotshape BUY/AL"
        return sig

    for m in re.finditer(
        r"plotshape\s*\(\s*([^,]+)\s*,.*?text\s*=\s*[\"'](?:AL|BUY)[\"']",
        code,
        flags=re.I | re.DOTALL,
    ):
        raw = _normalize_expr(m.group(1))
        sig = _finalize_condition(code, raw)
        sig.display_condition = sig.display_condition or "plotshape BUY/AL"
        return sig

    # plotshape(alCondition, ...) where variable is al*
    for m in re.finditer(r"plotshape\s*\(\s*(\w+)\s*,", code, flags=re.I):
        var = m.group(1)
        if re.search(rf"\b{re.escape(var)}\s*=", code, flags=re.I):
            if re.search(r"al|buy|long", var, flags=re.I):
                assign = re.search(
                    rf"{re.escape(var)}\s*=\s*([^\n]+)",
                    code,
                    flags=re.I,
                )
                if assign:
                    return PineALSignal(
                        _normalize_expr(assign.group(1)),
                        "variable",
                        var,
                    )
                return PineALSignal(var, "variable", var)

    # alertcondition(cond, ..., message="AL")
    for m in re.finditer(
        r"alertcondition\s*\(\s*([^,]+)\s*,.*?(?:message|title)\s*=\s*[\"'][^\"']*AL[^\"']*[\"']",
        code,
        flags=re.I | re.DOTALL,
    ):
        return PineALSignal(_normalize_expr(m.group(1)), "alertcondition")

    # Explicit: al = ... or buySignal = ... (skip names that only contain 'al' as substring)
    for m in re.finditer(
        r"\b(\w*(?:buy|long|_al|al_)\w*|\w*al)\s*=\s*([^\n;]+)",
        code,
        flags=re.I,
    ):
        name, expr = m.group(1), m.group(2)
        low = name.lower()
        if low.endswith("alma") or low.startswith("alma") or "alma" in low and low != "al":
            continue
        if re.search(r"\bal\b", name, flags=re.I) or low in (
            "buy",
            "buysignal",
            "buyflip",
            "long",
            "buysignal",
        ) or low.startswith("buy"):
            return PineALSignal(_normalize_expr(expr), "variable", name)

    # strategy.entry("AL", ...)
    for m in re.finditer(
        r"strategy\.entry\s*\(\s*[\"']AL[\"']\s*,\s*strategy\.long\s*,\s*when\s*=\s*([^)]+)\)",
        code,
        flags=re.I,
    ):
        return PineALSignal(_normalize_expr(m.group(1)), "strategy.entry")

    # Candle turns green (Fibo trend, etc.)
    green_first = _extract_candle_green_first(code)
    if green_first:
        return green_first

    return None
