"""Market cap lookup (parallel fast_info)."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import yfinance as yf

logger = logging.getLogger(__name__)

MAX_CAP_WORKERS = 24


def _fetch_one_cap_yf(yf_ticker: str, symbol: str) -> tuple[str, float | None]:
    try:
        t = yf.Ticker(yf_ticker)
        cap = None
        try:
            fi = t.fast_info
            cap = getattr(fi, "market_cap", None) or fi.get("market_cap")
        except Exception:
            pass
        if cap is None:
            info = t.info or {}
            cap = info.get("marketCap")
        if cap is None or cap <= 0:
            return symbol, None
        return symbol, float(cap)
    except Exception:
        return symbol, None


def fetch_market_caps(symbols: list[str], universe: str = "sp500") -> dict[str, float]:
    from app.services.ticker_format import to_yf_ticker

    caps: dict[str, float] = {}
    if not symbols:
        return caps

    workers = min(MAX_CAP_WORKERS, max(4, len(symbols) // 20))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_fetch_one_cap_yf, to_yf_ticker(s, universe), s): s for s in symbols
        }
        for fut in as_completed(futures):
            sym, cap = fut.result()
            if cap is not None:
                caps[sym] = cap
    return caps
