"""Binance Spot klines OHLCV for screening."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx
import pandas as pd

from app.services.http_ssl import default_ssl_context

from app.services.ticker_format import to_binance_pair

logger = logging.getLogger(__name__)

BINANCE_KLINES = "https://api.binance.com/api/v3/klines"
MAX_WORKERS = 10
KLINES_LIMIT = 1000

TIMEFRAME_TO_BINANCE: dict[str, str] = {
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "2h": "2h",
    "4h": "4h",
    "8h": "8h",
    "12h": "12h",
    "1d": "1d",
    "1wk": "1w",
    "1mo": "1M",
}

MIN_BARS: dict[str, int] = {
    "5m": 55,
    "15m": 55,
    "30m": 55,
    "1h": 55,
    "2h": 55,
    "4h": 55,
    "8h": 55,
    "12h": 55,
    "1d": 30,
    "1wk": 30,
    "1mo": 30,
}


def _fetch_klines(symbol: str, interval: str, limit: int = KLINES_LIMIT) -> pd.DataFrame | None:
    pair = to_binance_pair(symbol)
    if not pair:
        return None
    try:
        with httpx.Client(
            verify=default_ssl_context(),
            timeout=60.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; StockScreener/1.0)"},
        ) as client:
            response = client.get(
                BINANCE_KLINES,
                params={"symbol": pair, "interval": interval, "limit": limit},
            )
            if response.status_code == 400:
                return None
            response.raise_for_status()
            rows = response.json()
    except Exception as exc:
        logger.debug("Binance klines %s: %s", pair, exc)
        return None

    if not rows:
        return None

    df = pd.DataFrame(
        rows,
        columns=[
            "open_time",
            "Open",
            "High",
            "Low",
            "Close",
            "Volume",
            "close_time",
            "quote_volume",
            "trades",
            "taker_buy_base",
            "taker_buy_quote",
            "ignore",
        ],
    )
    for col in ("Open", "High", "Low", "Close", "Volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df.index = pd.DatetimeIndex(pd.to_datetime(df["open_time"], unit="ms", utc=True))
    out = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    return out if len(out) >= 10 else None


def fetch_ohlcv_batch_binance(
    symbols: list[str],
    timeframe: str,
) -> dict[str, pd.DataFrame]:
    interval = TIMEFRAME_TO_BINANCE.get(timeframe)
    if not interval:
        interval = TIMEFRAME_TO_BINANCE.get("1d", "1d")
    min_bars = MIN_BARS.get(timeframe, 30)

    out: dict[str, pd.DataFrame] = {}
    if not symbols:
        return out

    workers = min(MAX_WORKERS, max(4, len(symbols) // 15))

    def job(sym: str) -> tuple[str, pd.DataFrame | None]:
        return sym, _fetch_klines(sym, interval)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(job, sym): sym for sym in symbols}
        for fut in as_completed(futures):
            sym, frame = fut.result()
            if frame is not None and len(frame) >= min_bars:
                out[sym] = frame
    return out
