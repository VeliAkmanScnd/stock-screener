"""NASDAQ liquid universe: top N by ~20-day average dollar volume."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

from app.config import STORAGE_DIR

logger = logging.getLogger(__name__)

NASDAQ_LIQUID_TOP_N = 1000
NASDAQ_LIQUID_LOOKBACK_DAYS = 20
YF_CHUNK = 80
EXPORT_PATH = STORAGE_DIR / "symbol_cache" / "nasdaq_top1000.txt"


def _chunked(items: list[str], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _avg_dollar_volume(frame: pd.DataFrame, lookback: int = NASDAQ_LIQUID_LOOKBACK_DAYS) -> float:
    if frame is None or frame.empty:
        return 0.0
    df = frame.copy()
    df.columns = [str(c).title() for c in df.columns]
    if "Close" not in df.columns or "Volume" not in df.columns:
        return 0.0
    tail = df[["Close", "Volume"]].dropna().tail(lookback)
    if tail.empty:
        return 0.0
    return float((tail["Close"] * tail["Volume"]).mean())


def _split_batch(data: pd.DataFrame, tickers: list[str]) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    if data is None or data.empty:
        return out
    if isinstance(data.columns, pd.MultiIndex):
        # yfinance may use (OHLCV, ticker) or (ticker, OHLCV)
        level0 = {str(x) for x in data.columns.get_level_values(0)}
        if level0 & {"Open", "High", "Low", "Close", "Adj Close", "Volume"}:
            ticker_level = 1
        else:
            ticker_level = 0
        for sym in tickers:
            try:
                sub = data.xs(sym, axis=1, level=ticker_level, drop_level=True)
            except (KeyError, ValueError):
                continue
            if isinstance(sub, pd.Series):
                continue
            out[sym] = sub
    elif len(tickers) == 1:
        out[tickers[0]] = data
    return out


def rank_nasdaq_by_dollar_volume(
    symbols: tuple[str, ...] | list[str],
    *,
    top_n: int = NASDAQ_LIQUID_TOP_N,
    lookback_days: int = NASDAQ_LIQUID_LOOKBACK_DAYS,
) -> tuple[str, ...]:
    """Download ~1mo daily bars and keep the top_n by avg dollar volume."""
    clean = [str(s).strip().upper() for s in symbols if str(s).strip()]
    if not clean:
        return tuple()

    scores: dict[str, float] = {}
    total = len(clean)
    done = 0
    for batch in _chunked(clean, YF_CHUNK):
        done += len(batch)
        try:
            data = yf.download(
                tickers=batch,
                period="1mo",
                interval="1d",
                group_by="ticker",
                auto_adjust=True,
                threads=True,
                progress=False,
            )
        except Exception as exc:
            logger.warning("NASDAQ liquid batch failed (%s/%s): %s", done, total, exc)
            continue
        frames = _split_batch(data, batch)
        for sym in batch:
            scores[sym] = _avg_dollar_volume(frames.get(sym), lookback_days)
        logger.info(
            "NASDAQ liquid ranking progress %s/%s (scored=%s)",
            done,
            total,
            sum(1 for v in scores.values() if v > 0),
        )

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    positive = [sym for sym, score in ranked if score > 0]
    if len(positive) >= max(100, top_n // 5):
        selected = positive[:top_n]
    else:
        # Fallback: keep whatever scored, then fill alphabetically so scans still run.
        logger.warning(
            "NASDAQ liquid ranking weak (%s with volume); filling from full list",
            len(positive),
        )
        selected = positive[:]
        for sym in sorted(clean):
            if sym not in selected:
                selected.append(sym)
            if len(selected) >= top_n:
                break

    out = tuple(selected[:top_n])
    _export_list(out)
    logger.info(
        "NASDAQ liquid universe ready: %s symbols (lookback=%sd)",
        len(out),
        lookback_days,
    )
    return out


def _export_list(symbols: tuple[str, ...]) -> None:
    try:
        EXPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        header = (
            f"# NASDAQ top {len(symbols)} by ~{NASDAQ_LIQUID_LOOKBACK_DAYS}d avg $ volume\n"
            f"# updated={datetime.now(timezone.utc).isoformat()}\n"
        )
        EXPORT_PATH.write_text(header + "\n".join(symbols) + "\n", encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not export NASDAQ top list: %s", exc)


def read_exported_nasdaq_top_list() -> str | None:
    if not EXPORT_PATH.is_file():
        return None
    try:
        return EXPORT_PATH.read_text(encoding="utf-8")
    except OSError:
        return None
