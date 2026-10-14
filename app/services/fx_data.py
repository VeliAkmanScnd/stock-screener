"""FX majors plus gold and silver from Oanda via TradingView.

3m bars are built from 1m. Yahoo's gold series is the COMEX future, which
prints tens of dollars away from broker spot, so every pair uses OANDA.
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

OHLCV = ["Open", "High", "Low", "Close", "Volume"]


def yf_symbol(symbol: str) -> str:
    """Feed id. Kept under the old name so ticker helpers stay stable."""
    clean = clean_fx_symbol(symbol)
    if clean not in _PAIR_SET:
        return ""
    return f"{_EXCHANGE}:{clean}"


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


def _download_one(symbol: str, period: str, interval: str) -> pd.DataFrame | None:
    from borsapy._providers.tradingview import get_tradingview_provider

    raw = get_tradingview_provider().get_history(
        symbol=symbol,
        period=period,
        interval=interval,
        exchange=_EXCHANGE,
    )
    return _frame(raw)


def fetch_ohlcv_batch_fx(
    symbols: list[str],
    timeframe: str,
    on_progress: Callable[[int, int, str], None] | None = None,
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
                if built is not None:
                    frames[sym] = built
            else:
                frames[sym] = frame
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
    )
