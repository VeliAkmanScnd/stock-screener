"""Fetch latest prices for tracked symbols."""

from __future__ import annotations

import logging

import yfinance as yf

from app.services.batch_data import fetch_yfinance_ohlcv_batch
from app.services.binance_data import fetch_ohlcv_batch_binance
from app.services.price_utils import last_close_price, last_quote, yf_frame_for_ticker
from app.services.ticker_format import (
    clean_binance_symbol,
    clean_bist_symbol,
    is_binance_universe,
    is_bist_universe,
    to_yf_ticker,
)

logger = logging.getLogger(__name__)


def fetch_latest_prices(symbols: list[str], universe: str) -> dict[str, float]:
    quotes = fetch_latest_quotes(symbols, universe, interval="1d")
    return {sym: q["last"] for sym, q in quotes.items() if q.get("last") is not None}


def fetch_latest_quotes(
    symbols: list[str],
    universe: str,
    interval: str = "1d",
) -> dict[str, dict[str, float]]:
    if not symbols:
        return {}

    universe = (universe or "sp500").lower()
    interval = interval if interval in {"1h", "1d"} else "1d"
    out: dict[str, dict[str, float]] = {}

    if is_binance_universe(universe):
        frames = fetch_ohlcv_batch_binance(symbols, interval)
        for sym in symbols:
            key = clean_binance_symbol(sym)
            quote = last_quote(frames.get(key))
            if quote is None:
                quote = _quote_from_close(last_close_price(frames.get(key)))
            if quote is not None:
                out[key] = quote
        if interval == "1h" and len(out) < len(symbols):
            missing = [s for s in symbols if clean_binance_symbol(s) not in out]
            fallback = fetch_latest_quotes(missing, universe, interval="1d")
            out.update(fallback)
        return out

    if is_bist_universe(universe):
        frames = fetch_yfinance_ohlcv_batch(symbols, interval, universe)
        for sym in symbols:
            key = clean_bist_symbol(sym)
            quote = last_quote(frames.get(key))
            if quote is not None:
                out[key] = quote
        missing = [s for s in symbols if clean_bist_symbol(s) not in out]
        if missing and interval == "1h":
            fallback = fetch_latest_quotes(missing, universe, interval="1d")
            out.update(fallback)
            missing = [s for s in symbols if clean_bist_symbol(s) not in out]
        for sym in missing:
            try:
                t = yf.Ticker(to_yf_ticker(sym, universe))
                df = t.history(period="5d", interval=interval, auto_adjust=True)
                quote = last_quote(df)
                if quote is not None:
                    out[clean_bist_symbol(sym)] = quote
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
            interval=interval,
            auto_adjust=True,
            group_by="ticker",
            threads=True,
            progress=False,
        )
        if raw is not None and not raw.empty:
            if len(yf_tickers) == 1:
                sub = yf_frame_for_ticker(raw, yf_tickers[0])
                quote = last_quote(sub)
                if quote is not None:
                    out[symbols[0]] = quote
            else:
                for yf_sym in yf_tickers:
                    try:
                        sub = yf_frame_for_ticker(raw, yf_sym)
                        quote = last_quote(sub)
                        if quote is not None:
                            out[yf_map[yf_sym]] = quote
                    except (KeyError, ValueError):
                        continue
    except Exception as exc:
        logger.warning("Track quote batch failed (%s %s): %s", universe, interval, exc)

    if interval == "1h" and len(out) < len(symbols):
        missing = [s for s in symbols if s not in out]
        out.update(fetch_latest_quotes(missing, universe, interval="1d"))
    return out


def _quote_from_close(price: float | None) -> dict[str, float] | None:
    if price is None:
        return None
    return {"last": price, "high": price, "low": price}
