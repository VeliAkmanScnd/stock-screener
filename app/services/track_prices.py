"""Fetch latest prices for tracked symbols."""

from __future__ import annotations

import logging

import yfinance as yf

from app.services.batch_data import fetch_yfinance_ohlcv_batch
from app.services.binance_data import fetch_ohlcv_batch_binance
from app.services.price_utils import last_close_price, yf_frame_for_ticker
from app.services.ticker_format import (
    clean_binance_symbol,
    clean_bist_symbol,
    is_binance_universe,
    is_bist_universe,
    to_yf_ticker,
)

logger = logging.getLogger(__name__)


def fetch_latest_prices(symbols: list[str], universe: str) -> dict[str, float]:
    if not symbols:
        return {}

    universe = (universe or "sp500").lower()
    out: dict[str, float] = {}

    if is_binance_universe(universe):
        frames = fetch_ohlcv_batch_binance(symbols, "1d")
        for sym in symbols:
            key = clean_binance_symbol(sym)
            price = last_close_price(frames.get(key))
            if price is not None:
                out[key] = price
        return out

    if is_bist_universe(universe):
        frames = fetch_yfinance_ohlcv_batch(symbols, "1d", universe)
        for sym in symbols:
            key = clean_bist_symbol(sym)
            price = last_close_price(frames.get(key))
            if price is not None:
                out[key] = price
        missing = [s for s in symbols if clean_bist_symbol(s) not in out]
        for sym in missing:
            try:
                t = yf.Ticker(to_yf_ticker(sym, universe))
                df = t.history(period="5d", interval="1d", auto_adjust=True)
                price = last_close_price(df)
                if price is not None:
                    out[clean_bist_symbol(sym)] = price
            except Exception:
                continue
        return out

    yf_tickers = [to_yf_ticker(s, universe) for s in symbols]
    yf_map = {to_yf_ticker(s, universe): s for s in symbols}
    tickers_str = " ".join(yf_tickers)
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
        if len(yf_tickers) == 1:
            sub = yf_frame_for_ticker(raw, yf_tickers[0])
            price = last_close_price(sub)
            if price is not None:
                out[symbols[0]] = price
        else:
            for yf_sym in yf_tickers:
                try:
                    sub = yf_frame_for_ticker(raw, yf_sym)
                    price = last_close_price(sub)
                    if price is not None:
                        out[yf_map[yf_sym]] = price
                except (KeyError, ValueError):
                    continue
    except Exception as exc:
        logger.warning("Track price batch failed (%s): %s", universe, exc)

    return out
