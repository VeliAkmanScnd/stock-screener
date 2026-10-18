"""Batch OHLCV download and active-symbol validation."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Callable

import pandas as pd
import yfinance as yf

from app.config import DEFAULT_LOOKBACK_DAYS
from app.services.data_fetcher import INTRADAY_MIN_BARS, INTRADAY_PERIOD, INTRADAY_TIMEFRAMES
from app.services.ticker_format import (
    from_yf_ticker,
    is_binance_universe,
    is_bist_universe,
    is_fx_universe,
    is_viop_universe,
    to_yf_ticker,
)

logger = logging.getLogger(__name__)

YF_CHUNK_SIZE = 100
OHLCV_COLS = ["Open", "High", "Low", "Close", "Volume"]

# Built from 1h bars via pandas resample (yfinance has no native 2h/4h/8h/12h)
RESAMPLED_TIMEFRAMES: dict[str, str] = {
    "2h": "2h",
    "4h": "4h",
    "8h": "8h",
    "12h": "12h",
}
RESAMPLED_SOURCE_PERIOD = "730d"
RESAMPLED_SOURCE_INTERVAL = "1h"

# Bar length in minutes (for volume window aggregation)
BAR_MINUTES: dict[str, int] = {
    "3m": 3,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "2h": 120,
    "4h": 240,
    "8h": 480,
    "12h": 720,
    "1d": 390,
    "1wk": 1950,
    "1mo": 8400,
}

# Max age of last bar before symbol treated as delisted / stale
STALE_MULTIPLIER: dict[str, timedelta] = {
    "3m": timedelta(days=3),
    "5m": timedelta(days=3),
    "15m": timedelta(days=5),
    "30m": timedelta(days=7),
    "1h": timedelta(days=10),
    "2h": timedelta(days=12),
    "4h": timedelta(days=14),
    "8h": timedelta(days=18),
    "12h": timedelta(days=21),
    "1d": timedelta(days=8),
    "1wk": timedelta(days=21),
    "1mo": timedelta(days=45),
}


def _normalize_frame(df: pd.DataFrame) -> pd.DataFrame | None:
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        return None
    df = df.rename(columns=str.title)
    if not set(OHLCV_COLS).issubset(df.columns):
        return None
    out = df[OHLCV_COLS].dropna(how="all")
    return out if len(out) >= 10 else None


def _split_download(
    data: pd.DataFrame,
    yf_tickers: list[str],
    universe: str,
) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    if data is None or data.empty:
        return out

    if isinstance(data.columns, pd.MultiIndex):
        for yf_sym in yf_tickers:
            try:
                sub = data.xs(yf_sym, axis=1, level=0, drop_level=True)
                frame = _normalize_frame(sub)
                if frame is not None:
                    out[from_yf_ticker(yf_sym, universe)] = frame
            except (KeyError, ValueError):
                continue
    else:
        frame = _normalize_frame(data)
        if frame is not None and len(yf_tickers) == 1:
            out[from_yf_ticker(yf_tickers[0], universe)] = frame
    return out


def _asof_naive(asof: pd.Timestamp | None) -> pd.Timestamp | None:
    """Clock in the same naive zone as BIST/VIOP bars (Europe/Istanbul)."""
    if asof is None:
        return None
    ts = pd.Timestamp(asof)
    if ts.tzinfo is not None:
        ts = ts.tz_convert("Europe/Istanbul").tz_localize(None)
    return ts


def _drop_trailing_open_bucket(
    source: pd.DataFrame,
    agg: pd.DataFrame,
    rule: str,
    *,
    asof: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Drop a trailing bucket whose close is not final yet.

    A 15m bar is built from 5m bars, and its close is the last 5m close in the
    window. If that 5m bar has not printed, an earlier 5m close stands in for
    it. If the 5m bar is present but still the live last trade, that print can
    sit through a level and the finished 5m close can come back inside. On the
    15m chart both cases are a wick.

    ``asof`` is the clock in the same naive zone as ``source``. When it is set,
    the last bucket is kept only if the next source bar has started, or the
    clock is past the bucket end plus the settle gap. Callers that omit
    ``asof`` keep a bucket once its closing source slot exists.
    """
    if agg is None or agg.empty or source is None or len(source.index) < 2:
        return agg
    step = pd.Series(source.index).diff().median()
    if not isinstance(step, pd.Timedelta) or step <= pd.Timedelta(0):
        return agg
    try:
        width = pd.Timedelta(pd.tseries.frequencies.to_offset(rule))
    except (TypeError, ValueError):
        return agg
    if width <= step:
        return agg
    src = pd.DatetimeIndex(source.index)
    if src.tz is not None:
        src = src.tz_localize(None)
    clock = _asof_naive(asof)
    from app.services.bar_close import BAR_SETTLE_SECONDS

    settle = pd.Timedelta(seconds=BAR_SETTLE_SECONDS)
    out = agg
    for _ in range(3):
        if out.empty:
            break
        start = pd.Timestamp(out.index[-1])
        if start.tzinfo is not None:
            start = start.tz_localize(None)
        end = start + width
        slot = end - step
        pos = int(src.searchsorted(pd.Timestamp(end), side="left")) - 1
        slot_ok = pos >= 0 and src[pos] >= start and src[pos] >= slot
        if not slot_ok:
            out = out.iloc[:-1]
            continue
        nxt = int(src.searchsorted(pd.Timestamp(end), side="left"))
        if nxt < len(src):
            break
        if clock is None or clock >= end + settle:
            break
        out = out.iloc[:-1]
    return out


def _resample_ohlcv(
    df: pd.DataFrame,
    rule: str,
    *,
    asof: pd.Timestamp | None = None,
) -> pd.DataFrame | None:
    if df is None or df.empty:
        return None
    work = df.copy()
    if work.index.tz is not None:
        work.index = work.index.tz_localize(None)
    agg = work.resample(rule, label="left", closed="left").agg(
        {
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum",
        }
    )
    agg = agg.dropna(subset=["Close"])
    agg = _drop_trailing_open_bucket(work, agg, rule, asof=asof)
    return agg if len(agg) >= 10 else None


def _yf_download_period(
    symbols: list[str],
    *,
    universe: str,
    period: str,
    interval: str,
    resample_rule: str | None,
    on_progress: Callable[[int, int, str], None] | None,
    progress_offset: int,
    progress_total: int,
) -> dict[str, pd.DataFrame]:
    all_frames: dict[str, pd.DataFrame] = {}
    done = progress_offset
    chunk_size = 50 if is_bist_universe(universe) else YF_CHUNK_SIZE
    for i in range(0, len(symbols), chunk_size):
        chunk = symbols[i : i + chunk_size]
        yf_chunk = [to_yf_ticker(s, universe) for s in chunk]
        yf_chunk = [t for t in yf_chunk if t]
        if yf_chunk:
            tickers = " ".join(yf_chunk)
            try:
                raw = yf.download(
                    tickers=tickers,
                    period=period,
                    interval=interval,
                    auto_adjust=True,
                    group_by="ticker",
                    threads=True,
                    progress=False,
                )
                chunk_frames = _split_download(raw, yf_chunk, universe)
                if resample_rule:
                    for sym, frame in chunk_frames.items():
                        resampled = _resample_ohlcv(frame, resample_rule)
                        if resampled is not None:
                            all_frames[sym] = resampled
                else:
                    all_frames.update(chunk_frames)
            except Exception as exc:
                logger.warning("Batch download chunk failed: %s", exc)
        done += len(chunk)
        if on_progress:
            label = chunk[-1] if chunk else ""
            on_progress(min(done, progress_total), progress_total, label)
    return all_frames


def fetch_yfinance_ohlcv_batch(
    symbols: list[str],
    timeframe: str,
    universe: str = "sp500",
    on_progress: Callable[[int, int, str], None] | None = None,
    progress_offset: int = 0,
    progress_total: int | None = None,
    on_frames: Callable[[dict[str, pd.DataFrame]], None] | None = None,
) -> dict[str, pd.DataFrame]:
    """Yahoo Finance batch download (US, BIST .IS, etc.)."""
    if not symbols:
        return {}

    from app.services.ohlcv_store import cached_ohlcv_batch

    resample_rule = RESAMPLED_TIMEFRAMES.get(timeframe)

    if resample_rule:
        period, interval, min_bars = RESAMPLED_SOURCE_PERIOD, RESAMPLED_SOURCE_INTERVAL, INTRADAY_MIN_BARS
    elif timeframe in INTRADAY_TIMEFRAMES:
        period, interval, min_bars = INTRADAY_PERIOD, timeframe, INTRADAY_MIN_BARS
    elif timeframe in ("1d", "1wk", "1mo"):
        period = f"{DEFAULT_LOOKBACK_DAYS}d" if timeframe == "1d" else "2y"
        interval, min_bars = timeframe, 30
    else:
        period, interval, min_bars = INTRADAY_PERIOD, timeframe, 30

    def fetch_period(
        batch: list[str],
        use_period: str,
        offset: int,
        total: int,
        on_chunk: Callable[[dict[str, pd.DataFrame]], None] | None = None,
    ) -> dict[str, pd.DataFrame]:
        del on_chunk
        return _yf_download_period(
            batch,
            universe=universe,
            period=use_period,
            interval=interval,
            resample_rule=resample_rule,
            on_progress=on_progress,
            progress_offset=offset,
            progress_total=total,
        )

    return cached_ohlcv_batch(
        namespace=f"yf_{universe}",
        timeframe=timeframe,
        symbols=symbols,
        min_bars=min_bars,
        full_period=period,
        fetch_period=fetch_period,
        on_progress=on_progress,
        progress_offset=progress_offset,
        progress_total=progress_total,
        on_frames=on_frames,
    )


def fetch_ohlcv_batch(
    symbols: list[str],
    timeframe: str,
    universe: str = "sp500",
    on_progress: Callable[[int, int, str], None] | None = None,
    bist_provider: str | None = None,
    on_frames: Callable[[dict[str, pd.DataFrame]], None] | None = None,
) -> dict[str, pd.DataFrame]:
    """Download many symbols in chunks (much faster than one-by-one)."""
    if not symbols:
        return {}

    if is_fx_universe(universe):
        from app.services.fx_data import fetch_ohlcv_batch_fx

        return fetch_ohlcv_batch_fx(
            symbols, timeframe, on_progress=on_progress, on_frames=on_frames
        )

    if is_binance_universe(universe):
        from app.services.binance_data import fetch_ohlcv_batch_binance

        return fetch_ohlcv_batch_binance(symbols, timeframe)

    if is_viop_universe(universe):
        from app.services.viop_data import fetch_ohlcv_batch_viop

        frames = fetch_ohlcv_batch_viop(
            symbols, timeframe, on_progress=on_progress, on_frames=on_frames
        )
        return {s: f for s, f in frames.items() if len(f) >= 30}

    if is_bist_universe(universe):
        from app.services.bist_data import fetch_ohlcv_batch_bist
        from app.services.twelvedata_client import MIN_BARS

        min_bars = MIN_BARS.get(timeframe, 30)
        frames = fetch_ohlcv_batch_bist(
            symbols,
            timeframe,
            on_progress=on_progress,
            provider_override=bist_provider,
            on_frames=on_frames,
        )
        return {s: f for s, f in frames.items() if len(f) >= min_bars}

    return fetch_yfinance_ohlcv_batch(
        symbols, timeframe, universe, on_progress=on_progress, on_frames=on_frames
    )


def bars_for_minutes(timeframe: str, minutes: int) -> int:
    bar = BAR_MINUTES.get(timeframe, 390)
    return max(1, int(minutes / bar))


def sum_volume_window(df: pd.DataFrame, timeframe: str, minutes: int) -> float:
    n = bars_for_minutes(timeframe, minutes)
    return float(df["Volume"].iloc[-n:].sum())


def validate_active(
    df: pd.DataFrame,
    timeframe: str,
    universe: str = "sp500",
) -> tuple[bool, str | None]:
    """Reject delisted, stale, or zero-liquidity symbols."""
    if df is None or df.empty:
        return False, "no_data"

    close = df["Close"].iloc[-1]
    if is_bist_universe(universe) or is_viop_universe(universe):
        min_price = 0.5
    elif is_binance_universe(universe) or is_fx_universe(universe):
        min_price = 0.0000001
    else:
        min_price = 0.05
    if pd.isna(close) or float(close) < min_price:
        return False, "invalid_price"

    last_ts = pd.Timestamp(df.index[-1])
    if last_ts.tzinfo is not None:
        last_ts = last_ts.tz_convert(None)
    now = pd.Timestamp.now("UTC").tz_localize(None)
    stale_limit = STALE_MULTIPLIER.get(timeframe, timedelta(days=8))
    if (is_bist_universe(universe) or is_viop_universe(universe)) and timeframe == "1d":
        stale_limit = timedelta(days=12)
    elif is_binance_universe(universe):
        stale_limit = STALE_MULTIPLIER.get(timeframe, timedelta(days=3)) * 2
    if (now - last_ts) > stale_limit:
        return False, "stale_delisted"

    if not is_viop_universe(universe) and not is_fx_universe(universe):
        recent_n = min(5, len(df))
        if float(df["Volume"].iloc[-recent_n:].sum()) <= 0:
            return False, "no_volume"

    return True, None
