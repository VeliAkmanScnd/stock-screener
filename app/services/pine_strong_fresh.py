"""Strong Low/High · Fresh · Hedef — last-bar break or swing-carry filter."""

from __future__ import annotations

import math
import re

import numpy as np
import pandas as pd

from app.services.pine_params import merge_pine_inputs

STRONG_FRESH_MARKER = "__STRONG_FRESH_LAST__"

_EVENT_LABELS = {
    "kirilim": "Strong kırıldı (trend değişimi)",
    "tasima": "Strong taşındı (yeni swing)",
    "ikisi": "Strong kırıldı veya taşındı",
}


def is_strong_fresh_script(code: str) -> bool:
    raw = re.sub(r"//.*?$", "", code or "", flags=re.MULTILINE)
    has_title = bool(re.search(r"Strong\s+Low/High", raw, flags=re.I))
    has_state = bool(re.search(r"\bstrongLow\b", raw) and re.search(r"\bstrongHigh\b", raw))
    has_pivot = bool(re.search(r"ta\.pivothigh\s*\(", raw, flags=re.I))
    return has_title and has_state and has_pivot


def _as_bool(val: str | None, default: bool) -> bool:
    if val is None:
        return default
    return str(val).strip().lower() in ("1", "true", "yes", "on")


def _as_int(val: str | None, default: int) -> int:
    try:
        return int(float(val)) if val is not None and str(val).strip() else default
    except (TypeError, ValueError):
        return default


def _event(raw: str | None) -> str:
    key = str(raw or "ikisi").strip().lower()
    aliases = {
        "kırılım": "kirilim",
        "kirilim": "kirilim",
        "break": "kirilim",
        "taşıma": "tasima",
        "tasima": "tasima",
        "swing": "tasima",
        "ikisi": "ikisi",
        "both": "ikisi",
    }
    return aliases.get(key, "ikisi")


def strong_fresh_params_from_script(pine_code: str, overrides: dict | None = None) -> dict:
    inputs = merge_pine_inputs(pine_code, overrides)
    extra = overrides or {}
    side = str(extra.get("scan_side") or inputs.get("scan_side") or "both").strip().lower()
    if side not in ("buy", "sell", "both"):
        side = "both"
    event = _event(str(extra.get("sinyal") or inputs.get("sinyal") or "ikisi"))
    return {
        "pivot_len": max(1, min(50, _as_int(inputs.get("pivotLen"), 5))),
        "max_geri": max(20, min(480, _as_int(inputs.get("maxGeri"), 400))),
        "close_break": _as_bool(inputs.get("kirilimKapanis"), True),
        "event": event,
        "side": side,
    }


def strong_fresh_display_label(pine_code: str, overrides: dict | None = None) -> str:
    params = strong_fresh_params_from_script(pine_code, overrides)
    label = _EVENT_LABELS.get(params["event"], _EVENT_LABELS["ikisi"])
    side = {"buy": "AL", "sell": "SAT", "both": "AL+SAT"}.get(params["side"], "AL+SAT")
    how = "kapanış" if params["close_break"] else "fitil"
    return f"{label} · {side} · {how} · swing {params['pivot_len']}"


def _pivots(high: np.ndarray, low: np.ndarray, length: int) -> tuple[np.ndarray, np.ndarray]:
    n = len(high)
    ph = np.full(n, np.nan)
    pl = np.full(n, np.nan)
    if length < 1 or n <= length * 2:
        return ph, pl
    for i in range(length * 2, n):
        center = i - length
        left_h = high[center - length : center]
        right_h = high[center + 1 : center + length + 1]
        if high[center] > np.nanmax(left_h) and high[center] > np.nanmax(right_h):
            ph[i] = high[center]
        left_l = low[center - length : center]
        right_l = low[center + 1 : center + length + 1]
        if low[center] < np.nanmin(left_l) and low[center] < np.nanmin(right_l):
            pl[i] = low[center]
    return ph, pl


def _level_moved(prev: float | None, cur: float | None) -> bool:
    """True when the stored strong price appears or changes. Clearing it is not a carry."""
    if cur is None:
        return False
    if prev is None:
        return True
    return abs(cur - prev) > max(1e-6, abs(cur) * 1e-8)


def _price_through(price: float, level: float | None, above: bool) -> bool:
    if level is None:
        return False
    return price > level if above else price < level


def _swing_known(pivots: np.ndarray, bar: int | None, pivot_len: int, i: int) -> bool | None:
    """Whether `bar` is a confirmed pivot. None when the right side is still open."""
    if bar is None:
        return None
    confirm = bar + pivot_len
    if confirm > i or confirm >= len(pivots):
        return None
    if confirm < 0:
        return False
    return bool(math.isfinite(pivots[confirm]))


def _extreme(
    high: np.ndarray,
    low: np.ndarray,
    i: int,
    from_bar: int | None,
    to_bar: int | None,
    want_low: bool,
    max_geri: int,
) -> tuple[float | None, int | None]:
    if from_bar is None or to_bar is None:
        return None, None
    a = min(from_bar, to_bar)
    b = max(from_bar, to_bar)
    oldest = max(i - max_geri, 0)
    if b > i:
        b = i
    if a < oldest:
        a = oldest
    if b < a or a < 0:
        return None, None
    series = low if want_low else high
    px = float(series[b])
    px_bar = b
    span = min(b - a, 480)
    for step in range(1, span + 1):
        bar_x = b - step
        v = float(series[bar_x])
        if (want_low and v < px) or (not want_low and v > px):
            px = v
            px_bar = bar_x
    if not math.isfinite(px):
        return None, None
    return px, px_bar


def strong_fresh_snapshot(df: pd.DataFrame, **params) -> dict:
    """Replay structure. Match the last closed bar."""
    event = _event(params.get("event"))
    side = str(params.get("side") or "both")
    pivot_len = int(params.get("pivot_len") or 5)
    max_geri = int(params.get("max_geri") or 400)
    close_break = bool(params.get("close_break", True))
    empty = {
        "pine_al": False,
        "strong_buy": False,
        "strong_sell": False,
        "strong_break": False,
        "strong_carry": False,
        "strong_event": event,
        "strong_side": side,
    }
    if df is None or len(df) < pivot_len * 2 + 5:
        return empty

    high = df["High"].to_numpy(dtype=float)
    low = df["Low"].to_numpy(dtype=float)
    close = df["Close"].to_numpy(dtype=float)
    n = len(high)
    ph, pl = _pivots(high, low, pivot_len)

    last_sh = None
    last_sh_bar = None
    last_sl = None
    last_sl_bar = None
    bias = 0
    strong_low = None
    strong_low_bar = None
    strong_high = None
    strong_high_bar = None
    weak_high = None
    weak_high_bar = None
    weak_low = None
    weak_low_bar = None

    break_buy = np.zeros(n, dtype=bool)
    break_sell = np.zeros(n, dtype=bool)
    carry_buy = np.zeros(n, dtype=bool)
    carry_sell = np.zeros(n, dtype=bool)

    for i in range(n):
        prev_strong_low = strong_low
        prev_strong_high = strong_high
        if math.isfinite(ph[i]):
            ph_bar = i - pivot_len
            ph_px = float(ph[i])
            bullish_leg = bias == 1 or strong_high is None or ph_px > strong_high
            if last_sh is not None and ph_px > last_sh and bullish_leg:
                s_low, s_low_bar = _extreme(high, low, i, last_sh_bar, ph_bar, True, max_geri)
                probe = close[i] if close_break else low[i]
                # A higher pivot that lifts strong low above the current price
                # would be "broken" by this same bar without the active strong
                # low having been closed through.
                instant = (
                    s_low is not None
                    and strong_low is not None
                    and s_low > strong_low
                    and not _price_through(probe, strong_low, False)
                    and _price_through(probe, s_low, False)
                )
                if s_low is not None and not instant:
                    strong_low = s_low
                    strong_low_bar = s_low_bar
                    if weak_high is None or ph_px >= weak_high:
                        weak_high = ph_px
                        weak_high_bar = ph_bar
                    bias = 1
                    weak_low = None
                    weak_low_bar = None
                    if strong_high is not None and ph_px > strong_high:
                        strong_high = None
                        strong_high_bar = None
            last_sh = ph_px
            last_sh_bar = ph_bar

        if math.isfinite(pl[i]):
            pl_bar = i - pivot_len
            pl_px = float(pl[i])
            bearish_leg = bias == -1 or strong_low is None or pl_px < strong_low
            if last_sl is not None and pl_px < last_sl and bearish_leg:
                s_high, s_high_bar = _extreme(high, low, i, last_sl_bar, pl_bar, False, max_geri)
                probe = close[i] if close_break else high[i]
                # A lower pivot that drops strong high under the current price
                # would be "broken" by this same bar. A wick through the active
                # strong high does not count while close stays back below it.
                instant = (
                    s_high is not None
                    and strong_high is not None
                    and s_high < strong_high
                    and not _price_through(probe, strong_high, True)
                    and _price_through(probe, s_high, True)
                )
                if s_high is not None and not instant:
                    swing = _swing_known(ph, s_high_bar, pivot_len, i)
                    # Don't drop an active strong high onto a candle high that
                    # never became a swing (LCID 3.93 -> 3.79). The next close
                    # would otherwise "break" that internal high.
                    keep = (
                        strong_high is not None
                        and s_high < strong_high
                        and swing is False
                        and not _price_through(probe, strong_high, True)
                    )
                    # Do not mirror this onto a rising strong low. That low is
                    # the trough between two higher highs, and it often is not
                    # a pivot of its own. Holding the old low blocks the later
                    # bearish swing (ASTOR 12 Oct: 176.60 never reached 199.75,
                    # so the 11:30 turn never fired).
                    if not keep:
                        strong_high = s_high
                        strong_high_bar = s_high_bar
                    if weak_low is None or pl_px <= weak_low:
                        weak_low = pl_px
                        weak_low_bar = pl_bar
                    bias = -1
                    weak_high = None
                    weak_high_bar = None
                    if strong_low is not None and pl_px < strong_low:
                        strong_low = None
                        strong_low_bar = None
            last_sl = pl_px
            last_sl_bar = pl_bar

        if bias == 1 and weak_high is not None and high[i] > weak_high:
            weak_high = float(high[i])
            weak_high_bar = i
        if bias == -1 and weak_low is not None and low[i] < weak_low:
            weak_low = float(low[i])
            weak_low_bar = i

        low_broken = strong_low is not None and (
            close[i] < strong_low if close_break else low[i] < strong_low
        )
        high_broken = strong_high is not None and (
            close[i] > strong_high if close_break else high[i] > strong_high
        )
        if low_broken:
            tepe = weak_high if weak_high is not None else float(high[i])
            tepe_bar = weak_high_bar if weak_high_bar is not None else i
            strong_high = tepe
            strong_high_bar = tepe_bar
            weak_low = float(low[i])
            weak_low_bar = i
            strong_low = None
            strong_low_bar = None
            weak_high = None
            weak_high_bar = None
            bias = -1
            break_sell[i] = True
        elif high_broken:
            origin = strong_high_bar if strong_high_bar is not None else i
            dip, dip_bar = _extreme(high, low, i, origin, i, True, max_geri)
            strong_low = dip if dip is not None else float(low[i])
            strong_low_bar = dip_bar if dip_bar is not None else i
            weak_high = float(high[i])
            weak_high_bar = i
            strong_high = None
            strong_high_bar = None
            weak_low = None
            weak_low_bar = None
            bias = 1
            break_buy[i] = True

        # Carry only when the drawn strong price changes.
        # A lower strong-high after price has already left that high is the
        # same leg (weak low keeps updating); it is not a new swing.
        if not break_buy[i] and not break_sell[i]:
            moved_low = _level_moved(prev_strong_low, strong_low)
            moved_high = _level_moved(prev_strong_high, strong_high)
            if (
                moved_high
                and prev_strong_high is not None
                and strong_high is not None
                and strong_high < prev_strong_high
                and i > 0
                and close[i - 1] < prev_strong_high
            ):
                moved_high = False
            if moved_low and not moved_high:
                carry_buy[i] = True
            elif moved_high and not moved_low:
                carry_sell[i] = True
            elif moved_low and moved_high:
                if bias >= 0:
                    carry_buy[i] = True
                else:
                    carry_sell[i] = True
    return _finish(empty, event, side, break_buy, break_sell, carry_buy, carry_sell)


def _finish(empty, event, side, break_buy, break_sell, carry_buy, carry_sell) -> dict:
    if event == "kirilim":
        buy = bool(break_buy[-1])
        sell = bool(break_sell[-1])
    elif event == "tasima":
        buy = bool(carry_buy[-1])
        sell = bool(carry_sell[-1])
    else:
        buy = bool(break_buy[-1] or carry_buy[-1])
        sell = bool(break_sell[-1] or carry_sell[-1])
    if side == "buy":
        sell = False
    elif side == "sell":
        buy = False
    out = dict(empty)
    out.update(
        {
            "pine_al": buy or sell,
            "strong_buy": buy,
            "strong_sell": sell,
            "strong_break": bool(break_buy[-1] or break_sell[-1]),
            "strong_carry": bool(carry_buy[-1] or carry_sell[-1]),
            "strong_event": event,
            "strong_side": side,
        }
    )
    return out


def ensure_strong_fresh_script() -> None:
    """Keep the example script available in the Pine list."""
    from pathlib import Path

    from app.config import BASE_DIR
    from app.database import PineScript, SessionLocal
    from app.services.pine_storage import save_pine_script

    path = BASE_DIR / "examples" / "strong_fresh_hedef.txt"
    if not path.is_file():
        return
    content = path.read_text(encoding="utf-8")
    if not is_strong_fresh_script(content):
        return
    label = strong_fresh_display_label(content)
    db = SessionLocal()
    try:
        row = (
            db.query(PineScript)
            .filter(PineScript.name == "Strong Fresh Hedef")
            .order_by(PineScript.id.asc())
            .first()
        )
        if row is None:
            save_pine_script(
                db,
                content=content,
                display_name="Strong Fresh Hedef",
                original_filename=path.name,
                al_condition=label,
                al_source="strong_fresh",
            )
            return
        changed = (row.pine_content or "") != content or row.al_source != "strong_fresh"
        if not changed:
            return
        row.pine_content = content
        row.al_condition = label
        row.al_source = "strong_fresh"
        row.filename = path.name
        if row.file_path:
            dest = Path(row.file_path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
        db.commit()
    finally:
        db.close()


def strong_fresh_from_script(
    df: pd.DataFrame,
    pine_code: str,
    overrides: dict | None = None,
) -> bool:
    params = strong_fresh_params_from_script(pine_code, overrides)
    return bool(strong_fresh_snapshot(df, **params).get("pine_al"))
