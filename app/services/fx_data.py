"""FX majors plus gold and silver via TradingView.

Live scans use OANDA (broker spot vs COMEX). Market Bias tester / backtests
use ICMARKETS so charts match ICMARKETS:XAUUSD style TradingView history.
3m bars are built from 1m.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

import pandas as pd

from app.services.batch_data import _resample_ohlcv
from app.services.ticker_format import clean_fx_symbol

logger = logging.getLogger(__name__)

FX_PAIRS: tuple[str, ...] = (
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "USDCHF",
    "AUDUSD",
    "USDCAD",
    "NZDUSD",
    "XAUUSD",
    "XAGUSD",
)
_PAIR_SET = frozenset(FX_PAIRS)
_EXCHANGE = "OANDA"
FX_BACKTEST_EXCHANGE = "ICMARKETS"
_FX_PAIR_LABELS = {
    "EURUSD": "Euro / Dolar",
    "GBPUSD": "Sterlin / Dolar",
    "USDJPY": "Dolar / Yen",
    "USDCHF": "Dolar / Frank",
    "AUDUSD": "Avustralya Doları",
    "USDCAD": "Dolar / Kanada",
    "NZDUSD": "Yeni Zelanda Doları",
    "XAUUSD": "Altın",
    "XAGUSD": "Gümüş",
}

OHLCV = ["Open", "High", "Low", "Close", "Volume"]


def is_fx_pair(symbol: str) -> bool:
    return clean_fx_symbol(symbol) in _PAIR_SET


def list_fx_tester_contracts() -> list[dict[str, str]]:
    """Optimize/tester datalist rows — ICMARKETS continuous pairs."""
    return [
        {
            "ticker": pair,
            "contract": pair,
            "name": _FX_PAIR_LABELS.get(pair, pair),
            "market": "fx",
            "tv_symbol": f"{FX_BACKTEST_EXCHANGE}:{pair}",
        }
        for pair in FX_PAIRS
    ]


def yf_symbol(symbol: str) -> str:
    """Feed id. Kept under the old name so ticker helpers stay stable."""
    clean = clean_fx_symbol(symbol)
    if clean not in _PAIR_SET:
        return ""
    return f"{_EXCHANGE}:{clean}"


def backtest_tv_symbol(symbol: str) -> str:
    clean = clean_fx_symbol(symbol)
    if clean not in _PAIR_SET:
        return ""
    return f"{FX_BACKTEST_EXCHANGE}:{clean}"


def display_symbol(feed: str) -> str:
    text = str(feed or "").strip().upper()
    if ":" in text:
        text = text.split(":")[-1]
    return text if text in _PAIR_SET else ""


def _istanbul_naive(df: pd.DataFrame) -> pd.DataFrame:
    """Store bars on the Istanbul clock so labels match the rest of the app."""
    work = df.copy()
    if work.index.tz is None:
        work.index = work.index.tz_localize("UTC")
    work.index = work.index.tz_convert("Europe/Istanbul").tz_localize(None)
    return work


def _frame(df: pd.DataFrame | None) -> pd.DataFrame | None:
    if df is None or df.empty:
        return None
    work = df.rename(columns=str.title)
    if "Volume" not in work.columns:
        work["Volume"] = 0.0
    if not set(OHLCV).issubset(work.columns):
        return None
    out = _istanbul_naive(work[OHLCV].dropna(how="all"))
    return out if not out.empty else None


def _download_spec(timeframe: str) -> tuple[str, str, str | None]:
    """Return TradingView period, interval, and optional resample rule.

    The provider counts a session day as 8.5 hours, so these periods ask for
    enough bars to cover a 24-hour FX book.
    """
    if timeframe == "3m":
        return "5d", "1m", "3min"
    if timeframe == "5m":
        return "1mo", "5m", None
    if timeframe == "15m":
        return "3mo", "15m", None
    if timeframe == "30m":
        return "6mo", "30m", None
    if timeframe in ("1h", "60m"):
        return "1y", "1h", None
    if timeframe == "4h":
        return "2y", "4h", None
    if timeframe == "1wk":
        return "5y", "1wk", None
    if timeframe == "1mo":
        return "10y", "1mo", None
    return "2y", "1d", None


def _download_one(
    symbol: str,
    period: str,
    interval: str,
    *,
    exchange: str | None = None,
) -> pd.DataFrame | None:
    from borsapy._providers.tradingview import get_tradingview_provider

    from app.services.borsapy_client import _TV_SLOTS

    with _TV_SLOTS:
        raw = get_tradingview_provider().get_history(
            symbol=symbol,
            period=period,
            interval=interval,
            exchange=exchange or _EXCHANGE,
        )
    return _frame(raw)


def fetch_ohlcv_one_fx_backtest(
    symbol: str,
    timeframe: str,
    period: str = "60d",
) -> pd.DataFrame | None:
    """Single-pair ICMARKETS history for Market Bias tester."""
    from app.services.borsapy_client import (
        _borsapy_backtest_period,
        _normalize_frame,
        backtest_period_days,
        ensure_tradingview_auth,
    )

    clean = clean_fx_symbol(symbol)
    if clean not in _PAIR_SET:
        return None
    ensure_tradingview_auth()
    want_days = backtest_period_days(period)
    tv_period = _borsapy_backtest_period(period)
    # Prefer native TF; for short windows try 5m→15m/30m for denser wicks.
    attempts: list[tuple[str, str | None]] = [(timeframe, None)]
    if timeframe == "15m" and want_days <= 75:
        attempts = [("5m", "15min"), ("15m", None)]
    elif timeframe == "30m" and want_days <= 75:
        attempts = [("5m", "30min"), ("30m", None)]
    elif timeframe == "3m":
        attempts = [("1m", "3min")]

    best: pd.DataFrame | None = None
    best_span = -1
    asof = pd.Timestamp.now(tz="Europe/Istanbul")
    for interval, rule in attempts:
        try:
            frame = _download_one(
                clean,
                tv_period,
                interval,
                exchange=FX_BACKTEST_EXCHANGE,
            )
        except Exception as exc:
            logger.warning(
                "ICMARKETS backtest %s %s %s failed: %s",
                clean,
                timeframe,
                interval,
                exc,
            )
            continue
        if frame is None or frame.empty:
            continue
        if rule:
            frame = _resample_ohlcv(frame, rule, asof=asof)
        norm = _normalize_frame(frame) if frame is not None else None
        if norm is None or len(norm) < 30:
            continue
        try:
            span = max(0, int((norm.index[-1] - norm.index[0]).days))
        except Exception:
            span = 0
        if rule and span >= min(want_days, 35):
            return norm
        if span > best_span:
            best = norm
            best_span = span
    return best


def fetch_ohlcv_batch_fx(
    symbols: list[str],
    timeframe: str,
    on_progress: Callable[[int, int, str], None] | None = None,
    on_frames: Callable[[dict[str, pd.DataFrame]], None] | None = None,
) -> dict[str, pd.DataFrame]:
    from app.services.bar_close import seconds_until_bar_settled
    from app.services.borsapy_client import ensure_tradingview_auth
    from app.services.ohlcv_store import cached_ohlcv_batch

    wanted = []
    for symbol in symbols:
        clean = clean_fx_symbol(symbol)
        if clean in _PAIR_SET:
            wanted.append(clean)
    if not wanted:
        return {}

    ensure_tradingview_auth()
    period, interval, rule = _download_spec(timeframe)
    wait = seconds_until_bar_settled(timeframe)
    if wait > 0:
        logger.info("Waiting %.0fs for the FX %s bar to settle", wait, timeframe)
        time.sleep(wait)

    def fetch_period(
        batch: list[str],
        use_period: str,
        offset: int,
        total: int,
        on_chunk: Callable[[dict[str, pd.DataFrame]], None] | None = None,
    ) -> dict[str, pd.DataFrame]:
        frames: dict[str, pd.DataFrame] = {}
        for sym in batch:
            try:
                frame = _download_one(sym, use_period, interval)
            except Exception as exc:
                logger.warning("OANDA %s %s failed: %s", sym, interval, exc)
                frame = None
            if frame is None:
                continue
            if rule:
                asof = pd.Timestamp.now(tz="Europe/Istanbul")
                built = _resample_ohlcv(frame, rule, asof=asof)
            else:
                built = frame
            if built is None:
                continue
            frames[sym] = built
            if on_chunk:
                on_chunk({sym: built})
        if on_progress:
            on_progress(min(offset + len(batch), total), total, batch[-1] if batch else "")
        return frames

    return cached_ohlcv_batch(
        namespace="oanda_fx",
        timeframe=timeframe,
        symbols=wanted,
        min_bars=55 if timeframe not in ("1d", "1wk") else 30,
        full_period=period,
        fetch_period=fetch_period,
        on_progress=on_progress,
        on_frames=on_frames,
    )
