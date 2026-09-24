"""Universe benchmark index mapping and price fetch."""

from __future__ import annotations

import logging
from typing import Any

import yfinance as yf

from app.services.price_utils import last_close_price, yf_frame_for_ticker

logger = logging.getLogger(__name__)

BENCHMARKS: dict[str, dict[str, str]] = {
    "bist": {"symbol": "XU100.IS", "label": "BIST100"},
    "viop": {"symbol": "XU030.IS", "label": "XU030"},
    "sp500": {"symbol": "^GSPC", "label": "S&P 500"},
    "nasdaq": {"symbol": "^NDX", "label": "NAS100"},
    "nyse": {"symbol": "^NYA", "label": "NYSE"},
    "all_us": {"symbol": "^GSPC", "label": "S&P 500"},
    "binance": {"symbol": "BTC-USD", "label": "BTC"},
    "custom": {"symbol": "^GSPC", "label": "S&P 500"},
}


def get_benchmark_config(universe: str) -> dict[str, str] | None:
    key = (universe or "").lower()
    if key in BENCHMARKS:
        return BENCHMARKS[key]
    if key in ("borsa_istanbul", "istanbul", "borsa"):
        return BENCHMARKS["bist"]
    if key in ("vadeli", "viop_futures"):
        return BENCHMARKS["viop"]
    if key in ("binance_spot", "crypto"):
        return BENCHMARKS["binance"]
    if key in ("all", "us"):
        return BENCHMARKS["all_us"]
    return None


def fetch_benchmark_price(universe: str) -> float | None:
    prices = fetch_benchmark_prices([universe])
    return prices.get((universe or "").lower())


def fetch_benchmark_prices(universes: list[str]) -> dict[str, float]:
    """Return latest benchmark price per universe key."""
    out: dict[str, float] = {}
    sym_to_keys: dict[str, list[str]] = {}
    for universe in universes:
        key = (universe or "").lower()
        cfg = get_benchmark_config(key)
        if not cfg:
            continue
        sym = cfg["symbol"]
        sym_to_keys.setdefault(sym, []).append(key)

    if not sym_to_keys:
        return out

    symbols = list(sym_to_keys.keys())
    if len(symbols) == 1:
        sym = symbols[0]
        try:
            df = yf.Ticker(sym).history(period="5d", interval="1d", auto_adjust=True)
            price = last_close_price(df)
            if price is not None:
                for key in sym_to_keys[sym]:
                    out[key] = price
        except Exception as exc:
            logger.warning("Benchmark fetch failed (%s): %s", sym, exc)
        return out

    tickers_str = " ".join(symbols)
    try:
        raw = yf.download(
            tickers=tickers_str,
            period="5d",
            interval="1d",
            auto_adjust=True,
            group_by="ticker",
            threads=True,
            progress=False,
        )
        if raw is None or raw.empty:
            return out
        for sym in symbols:
            try:
                sub = yf_frame_for_ticker(raw, sym)
                price = last_close_price(sub)
                if price is not None:
                    for key in sym_to_keys[sym]:
                        out[key] = price
            except (KeyError, ValueError):
                try:
                    df = yf.Ticker(sym).history(period="5d", interval="1d", auto_adjust=True)
                    price = last_close_price(df)
                    if price is not None:
                        for key in sym_to_keys[sym]:
                            out[key] = price
                except Exception:
                    continue
    except Exception as exc:
        logger.warning("Benchmark batch fetch failed: %s", exc)
        for sym in symbols:
            try:
                df = yf.Ticker(sym).history(period="5d", interval="1d", auto_adjust=True)
                price = last_close_price(df)
                if price is not None:
                    for key in sym_to_keys[sym]:
                        out[key] = price
            except Exception:
                continue
    return out


def benchmark_meta(universe: str) -> dict[str, Any] | None:
    cfg = get_benchmark_config(universe)
    if not cfg:
        return None
    return {"symbol": cfg["symbol"], "label": cfg["label"]}
