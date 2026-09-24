"""Screening engine: batch data + built-in filters + Pine AL."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import pandas as pd

from app.config import MAX_SYMBOLS_PER_SCAN
from app.services.batch_data import fetch_ohlcv_batch, sum_volume_window, validate_active
from app.services.data_fetcher import get_universe_symbols, parse_symbol_list
from app.services.ticker_format import is_bist_universe, is_binance_universe, is_viop_universe
from app.services.indicators import build_indicator_frame, crossover, ema
from app.services.market_caps import fetch_market_caps
from app.services.pine_evaluator import PineEvalError, evaluate_pine_al
from app.utils.json_safe import json_safe


@dataclass
class FilterRule:
    id: str
    enabled: bool = True
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScanRequest:
    symbols: list[str] | None = None
    universe: str = "sp500"
    custom_symbols: str = ""
    custom_source_universe: str | None = None
    timeframe: str = "1d"
    filters: list[FilterRule] = field(default_factory=list)
    pine_script_id: int | None = None
    pine_condition: str | None = None
    require_pine_al: bool = False
    pine_input_overrides: dict[str, Any] = field(default_factory=dict)
    max_symbols: int = MAX_SYMBOLS_PER_SCAN
    bist_data_provider: str | None = None


@dataclass
class ScanResult:
    symbol: str
    price: float
    signals: dict[str, Any]
    matched: bool


@dataclass
class ScanStats:
    requested: int = 0
    downloaded: int = 0
    skipped_inactive: int = 0
    scanned: int = 0
    matched: int = 0
    skip_reasons: dict[str, int] = field(default_factory=dict)


def _last(series: pd.Series) -> float:
    v = series.iloc[-1]
    return float(v) if pd.notna(v) else float("nan")


def _filter_enabled(filters: list[FilterRule], fid: str) -> bool:
    return any(f.enabled and f.id == fid for f in filters)


def apply_builtin_filters(
    df: pd.DataFrame,
    filters: list[FilterRule],
    *,
    timeframe: str,
    market_cap: float | None = None,
    market_universe: str = "sp500",
) -> tuple[bool, dict[str, Any]]:
    signals: dict[str, Any] = {}
    c = df["Close"]

    for f in filters:
        if not f.enabled:
            continue

        fid = f.id
        p = f.params

        if fid == "market_cap_min":
            default_min = (
                10_000_000_000
                if is_bist_universe(market_universe) or is_viop_universe(market_universe)
                else 300_000_000
            )
            min_val = float(p.get("min_usd", default_min))
            currency = (
                "TRY"
                if is_bist_universe(market_universe) or is_viop_universe(market_universe)
                else "USD"
            )
            signals["market_cap"] = market_cap
            signals["market_cap_currency"] = currency
            signals["market_cap_min"] = min_val
            if market_cap is None or market_cap < min_val:
                return False, signals

        elif fid == "volume_window_min":
            minutes = int(p.get("minutes", 240))
            min_vol = float(p.get("min_volume", 10000))
            vol = sum_volume_window(df, timeframe, minutes)
            signals["volume_window"] = vol
            signals["volume_window_minutes"] = minutes
            if vol < min_vol:
                return False, signals

        elif fid == "open_gap_min":
            min_pct = float(p.get("min_pct", 1.0))
            if len(df) < 2:
                return False, signals
            prev_close = df["Close"].iloc[-2]
            curr_open = df["Open"].iloc[-1]
            if pd.isna(prev_close) or pd.isna(curr_open) or not float(prev_close):
                return False, signals
            gap_pct = (float(curr_open) - float(prev_close)) / float(prev_close) * 100
            signals["open_gap_pct"] = round(gap_pct, 2)
            signals["open_gap_min_pct"] = min_pct
            if gap_pct <= min_pct:
                return False, signals

        elif fid == "ema_cross":
            fast = int(p.get("fast", 9))
            slow = int(p.get("slow", 21))
            ef = ema(c, fast)
            es = ema(c, slow)
            ok = bool(crossover(ef, es).iloc[-1])
            signals[f"ema_{fast}_{slow}_cross"] = ok
            if not ok:
                return False, signals

        elif fid == "price_above_ema":
            period = int(p.get("period", 50))
            col = f"ema_{period}"
            if col not in df.columns:
                return False, signals
            ok = bool(c.iloc[-1] > df[col].iloc[-1])
            signals[f"price_above_ema_{period}"] = ok
            if not ok:
                return False, signals

        elif fid == "rsi_range":
            lo, hi = float(p.get("min", 30)), float(p.get("max", 70))
            r = _last(df["rsi_14"])
            signals["rsi_14"] = r
            if not (lo <= r <= hi):
                return False, signals

        elif fid == "rsi_oversold_bounce":
            thresh = float(p.get("threshold", 30))
            r_now, r_prev = df["rsi_14"].iloc[-1], df["rsi_14"].iloc[-2]
            ok = bool(r_prev < thresh <= r_now)
            signals["rsi_bounce"] = ok
            if not ok:
                return False, signals

        elif fid == "adx_trend":
            min_adx = float(p.get("min", 25))
            a = _last(df["adx_14"])
            signals["adx_14"] = a
            if a < min_adx:
                return False, signals

        elif fid == "cci_range":
            lo, hi = float(p.get("min", -100)), float(p.get("max", 100))
            v = _last(df["cci_20"])
            signals["cci_20"] = v
            if not (lo <= v <= hi):
                return False, signals

        elif fid == "momentum_positive":
            m = _last(df["mom_10"])
            signals["mom_10"] = m
            if m <= 0:
                return False, signals

        elif fid == "price_above_alma":
            period = int(p.get("period", 9))
            if f"alma_{period}" in df.columns:
                alma_line = df[f"alma_{period}"]
            else:
                from app.services.indicators import alma

                alma_line = alma(c, period)
            ok = bool(c.iloc[-1] > alma_line.iloc[-1])
            signals[f"price_above_alma_{period}"] = ok
            if not ok:
                return False, signals

        elif fid == "alma_cross":
            fast = int(p.get("fast", 9))
            slow = int(p.get("slow", 21))
            af = df[f"alma_{fast}"] if f"alma_{fast}" in df.columns else df["alma_9"]
            if slow == 21:
                als = df["alma_21"]
            else:
                from app.services.indicators import alma

                als = alma(c, slow)
            ok = bool(crossover(af, als).iloc[-1])
            signals["alma_cross"] = ok
            if not ok:
                return False, signals

        elif fid == "atr_expansion":
            min_ratio = float(p.get("min_ratio", 1.1))
            atr_s = df["atr_14"]
            ratio = atr_s.iloc[-1] / atr_s.iloc[-6] if atr_s.iloc[-6] else 0
            signals["atr_ratio"] = float(ratio)
            if ratio < min_ratio:
                return False, signals

    return True, signals


def scan_market_universe(req: ScanRequest) -> str:
    """Market used for OHLCV/tickers when universe is custom."""
    u = (req.universe or "sp500").lower()
    if u == "custom" and req.custom_source_universe:
        return req.custom_source_universe.lower()
    return u


def resolve_symbols(req: ScanRequest) -> list[str]:
    if req.symbols:
        syms = req.symbols
    elif req.universe == "custom" and req.custom_symbols:
        syms = parse_symbol_list(req.custom_symbols, scan_market_universe(req))
    else:
        syms = get_universe_symbols(req.universe)

    return syms[: req.max_symbols]


def scan_dataframe(
    symbol: str,
    df: pd.DataFrame,
    req: ScanRequest,
    market_cap: float | None,
    pine_condition: str | None = None,
    pine_source: str | None = None,
    pine_code: str | None = None,
) -> ScanResult:
    df = build_indicator_frame(df)
    market = scan_market_universe(req)
    has_filters = any(f.enabled for f in req.filters)
    matched, signals = (
        apply_builtin_filters(
            df,
            req.filters,
            timeframe=req.timeframe,
            market_cap=market_cap,
            market_universe=market,
        )
        if has_filters
        else (True, {})
    )

    if market_cap is not None and "market_cap" not in signals:
        signals["market_cap"] = market_cap
        if is_bist_universe(market) or is_viop_universe(market):
            signals["market_cap_currency"] = "TRY"
        elif is_binance_universe(market):
            signals["market_cap_currency"] = "USD"
        else:
            signals["market_cap_currency"] = "USD"

    if pine_condition:
        try:
            overrides = req.pine_input_overrides or None
            if pine_source == "merged_triple" and pine_code:
                from app.services.pine_merged_triple import merged_triple_snapshot

                snap = merged_triple_snapshot(df, pine_code, overrides)
                signals.update(snap)
                pine_ok = bool(snap["merged_triple_buy"])
            elif pine_source == "bias_ts" and pine_code:
                from app.services.pine_bias_ts import bias_ts_params_from_script, bias_ts_snapshot

                snap = bias_ts_snapshot(df, **bias_ts_params_from_script(pine_code, overrides))
                signals.update(snap)
                pine_ok = bool(snap.get("pine_al"))
            elif pine_source == "candle_green_first" and pine_code:
                from app.services.pine_fibo import fibo_params_from_script, fibo_trend_snapshot

                snap = fibo_trend_snapshot(
                    df, **fibo_params_from_script(pine_code, overrides)
                )
                signals.update(snap)
                pine_ok = bool(snap["first_green_bar"])
            else:
                pine_ok = bool(
                    evaluate_pine_al(
                        df,
                        pine_condition,
                        source=pine_source,
                        pine_code=pine_code,
                        pine_input_overrides=overrides,
                    )
                )
                signals["pine_al"] = pine_ok
            if pine_source == "candle_green_first":
                signals["pine_al"] = pine_ok
                signals["pine_al_mode"] = "first_green_bar"
            matched = pine_ok if (req.require_pine_al and not has_filters) else (matched and pine_ok)
        except PineEvalError as e:
            signals["pine_al_error"] = str(e)
            matched = False

    return ScanResult(
        symbol=symbol,
        price=_last(df["Close"]),
        signals=json_safe(signals),
        matched=bool(matched),
    )


def run_scan(
    req: ScanRequest,
    pine_condition: str | None = None,
    pine_source: str | None = None,
    pine_code: str | None = None,
    progress_callback: Callable[[str, int, int, str], None] | None = None,
) -> tuple[list[ScanResult], ScanStats]:
    def report(phase: str, done: int, total: int, detail: str = "") -> None:
        if progress_callback:
            progress_callback(phase, done, total, detail)

    symbols = resolve_symbols(req)
    stats = ScanStats(requested=len(symbols))

    market = scan_market_universe(req)

    def on_download(done: int, total: int, symbol: str) -> None:
        report("downloading", done, total, symbol)

    bist_provider = req.bist_data_provider if is_bist_universe(market) else None
    frames = fetch_ohlcv_batch(
        symbols,
        req.timeframe,
        market,
        on_progress=on_download,
        bist_provider=bist_provider,
    )
    stats.downloaded = len(frames)

    active: dict[str, pd.DataFrame] = {}
    for sym, df in frames.items():
        ok, reason = validate_active(df, req.timeframe, market)
        if ok:
            active[sym] = df
        else:
            stats.skipped_inactive += 1
            key = reason or "inactive"
            stats.skip_reasons[key] = stats.skip_reasons.get(key, 0) + 1

    needs_cap = _filter_enabled(req.filters, "market_cap_min")
    caps = fetch_market_caps(list(active.keys()), market) if needs_cap else {}

    results: list[ScanResult] = []
    active_items = list(active.items())
    total_scan = len(active_items)
    for idx, (sym, df) in enumerate(active_items, start=1):
        stats.scanned += 1
        r = scan_dataframe(
            sym,
            df,
            req,
            caps.get(sym),
            pine_condition,
            pine_source,
            pine_code,
        )
        if r.matched:
            results.append(r)
            stats.matched += 1
        report("scanning", idx, total_scan, sym)

    results.sort(key=lambda x: x.symbol)
    return results, stats
