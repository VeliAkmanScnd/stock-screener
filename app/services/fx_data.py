"""FX majors plus gold and silver. 3m bars are built from 1m."""

from __future__ import annotations

import logging
import time
from typing import Callable

import pandas as pd
import yfinance as yf

from app.services.batch_data import _resample_ohlcv
from app.services.ticker_format import clean_fx_symbol

logger = logging.getLogger(__name__)

# Seven majors, then spot-style names for the metals. Yahoo has no XAUUSD/XAGUSD
# spot series; those two download the COMEX front futures (GC, SI).
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

_YF: dict[str, str] = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
    "USDCHF": "USDCHF=X",
    "AUDUSD": "AUDUSD=X",
    "USDCAD": "USDCAD=X",
    "NZDUSD": "NZDUSD=X",
    "XAUUSD": "GC=F",
    "XAGUSD": "SI=F",
}
_FROM_YF = {ticker: symbol for symbol, ticker in _YF.items()}

OHLCV = ["Open", "High", "Low", "Close", "Volume"]


def yf_symbol(symbol: str) -> str:
    return _YF.get(clean_fx_symbol(symbol), "")


def display_symbol(yf_ticker: str) -> str:
    return _FROM_YF.get(str(yf_ticker).strip(), "")


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
    if not set(OHLCV).issubset(work.columns):
        return None
    out = _istanbul_naive(work[OHLCV].dropna(how="all"))
    return out if not out.empty else None


def _split(raw: pd.DataFrame, yf_symbols: list[str]) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    if raw is None or raw.empty:
        return out
    if isinstance(raw.columns, pd.MultiIndex):
        for ticker in yf_symbols:
            try:
                sub = raw[ticker]
            except KeyError:
                continue
            frame = _frame(sub)
            symbol = display_symbol(ticker)
            if frame is not None and symbol:
                out[symbol] = frame
        return out
    frame = _frame(raw)
    if frame is not None and len(yf_symbols) == 1:
        symbol = display_symbol(yf_symbols[0])
        if symbol:
            out[symbol] = frame
    return out


def _download_spec(timeframe: str) -> tuple[str, str, str | None]:
    """Return Yahoo period, interval, and optional resample rule."""
    if timeframe == "3m":
        # Yahoo has no 3m bars. 1m history is only a few days.
        return "5d", "1m", "3min"
    if timeframe in ("5m", "15m", "30m"):
        return "60d", timeframe, None
    if timeframe in ("1h", "60m"):
        return "730d", "1h", None
    if timeframe == "1wk":
        return "2y", "1wk", None
    if timeframe == "1d":
        return "1y", "1d", None
    return "60d", timeframe, None


def fetch_ohlcv_batch_fx(
    symbols: list[str],
    timeframe: str,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> dict[str, pd.DataFrame]:
    from app.services.bar_close import seconds_until_bar_settled
    from app.services.ohlcv_store import cached_ohlcv_batch

    wanted = []
    for symbol in symbols:
        clean = clean_fx_symbol(symbol)
        if yf_symbol(clean):
            wanted.append(clean)
    if not wanted:
        return {}

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
        yf_batch = [yf_symbol(sym) for sym in batch if yf_symbol(sym)]
        download_period = "5d" if interval == "1m" else use_period
        try:
            raw = yf.download(
                yf_batch,
                period=download_period,
                interval=interval,
                group_by="ticker",
                auto_adjust=True,
                threads=False,
                progress=False,
            )
        except Exception as exc:
            logger.warning("FX download failed (%s): %s", yf_batch[:3], exc)
            raw = None
        frames = _split(raw, yf_batch) if raw is not None else {}
        if rule:
            asof = pd.Timestamp.now(tz="Europe/Istanbul")
            resampled: dict[str, pd.DataFrame] = {}
            for sym, frame in frames.items():
                built = _resample_ohlcv(frame, rule, asof=asof)
                if built is not None:
                    resampled[sym] = built
            frames = resampled
        if on_progress:
            on_progress(min(offset + len(batch), total), total, batch[-1] if batch else "")
        return frames

    return cached_ohlcv_batch(
        namespace="yf_fx",
        timeframe=timeframe,
        symbols=wanted,
        min_bars=55 if timeframe not in ("1d", "1wk") else 30,
        full_period=period,
        fetch_period=fetch_period,
        on_progress=on_progress,
    )
