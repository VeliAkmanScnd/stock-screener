"""VIOP contract list + OHLCV (borsapy quotes; history via dayanak / index)."""

from __future__ import annotations

import logging
from typing import Callable

import pandas as pd

from app.services.ticker_format import clean_viop_symbol, viop_underlying

logger = logging.getLogger(__name__)

OHLCV_COLS = ["Open", "High", "Low", "Close", "Volume"]


def _normalize_frame(df: pd.DataFrame) -> pd.DataFrame | None:
    if df is None or df.empty:
        return None
    work = df.rename(columns=str.title)
    if not set(OHLCV_COLS).issubset(work.columns):
        return None
    out = work[OHLCV_COLS].dropna(how="all")
    if out.index.tz is not None:
        out = out.copy()
        out.index = out.index.tz_localize(None)
    return out if len(out) >= 10 else None


def fetch_viop_symbols_live() -> tuple[str, ...]:
    """Nearest/most-liquid F_ contract per underlying (borsapy VIOP board)."""
    import borsapy as bp

    board = bp.VIOP()
    frames = [
        board.index_futures,
        board.stock_futures,
        board.currency_futures,
        board.commodity_futures,
    ]
    parts = [f for f in frames if f is not None and not f.empty]
    if not parts:
        raise ValueError("VIOP kontrat listesi boş")
    all_df = pd.concat(parts, ignore_index=True)
    if "code" not in all_df.columns:
        raise ValueError("VIOP tablo formatı beklenmedik")

    rows: list[tuple[str, str, float]] = []
    for _, row in all_df.iterrows():
        code = clean_viop_symbol(row.get("code") or "")
        if not code.startswith("F_"):
            continue
        und = viop_underlying(code)
        if not und:
            continue
        vol = float(row.get("volume_qty") or 0) or 0.0
        rows.append((und, code, vol))

    best: dict[str, tuple[str, float]] = {}
    for und, code, vol in rows:
        prev = best.get(und)
        if prev is None or vol > prev[1]:
            best[und] = (code, vol)

    out = tuple(sorted({code for code, _ in best.values()}))
    if len(out) < 5:
        raise ValueError(f"VIOP listesi eksik ({len(out)})")
    logger.info("VIOP front contracts: %d", len(out))
    return out


def _pick_frame(frames: dict[str, pd.DataFrame], *keys: str) -> pd.DataFrame | None:
    for key in keys:
        if key and key in frames:
            return frames[key]
    return None


def _usable(frame: pd.DataFrame | None) -> pd.DataFrame | None:
    if frame is None:
        return None
    return _normalize_frame(frame)


def _history_borsapy(symbol: str, timeframe: str) -> pd.DataFrame | None:
    from app.services.borsapy_client import fetch_ohlcv_batch_borsapy

    frames = fetch_ohlcv_batch_borsapy([symbol], timeframe)
    return _pick_frame(frames, symbol, clean_viop_symbol(symbol))


def _history_yahoo_underlying(underlying: str, timeframe: str) -> pd.DataFrame | None:
    """Yahoo has dayanak cash/index (.IS), not F_ futures codes."""
    from app.services.batch_data import fetch_yfinance_ohlcv_batch

    und = viop_underlying(underlying)
    if not und or und.startswith("F_"):
        return None
    frames = fetch_yfinance_ohlcv_batch([und], timeframe, "bist")
    return _pick_frame(frames, und)


def fetch_ohlcv_one_viop(symbol: str, timeframe: str) -> pd.DataFrame | None:
    """History via dayanak (cash/index). Contract premium is not available."""
    code = clean_viop_symbol(symbol)
    und = viop_underlying(code)
    candidates = []
    if und:
        candidates.append(und)
    if code and code != und:
        candidates.append(code)
    for candidate in candidates:
        try:
            frame = _usable(_history_borsapy(candidate, timeframe))
            if frame is not None:
                return frame
        except Exception as exc:
            logger.debug("VIOP borsapy %s: %s", candidate, exc)
        if not candidate.startswith("F_"):
            try:
                frame = _usable(_history_yahoo_underlying(candidate, timeframe))
                if frame is not None:
                    return frame
            except Exception as exc:
                logger.debug("VIOP yahoo %s: %s", candidate, exc)
    return None


def fetch_ohlcv_batch_viop(
    symbols: list[str],
    timeframe: str,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> dict[str, pd.DataFrame]:
    clean = [clean_viop_symbol(s) for s in symbols if clean_viop_symbol(s)]
    if not clean:
        return {}

    by_und: dict[str, list[str]] = {}
    for code in clean:
        by_und.setdefault(viop_underlying(code) or code, []).append(code)

    unique_und = list(by_und.keys())
    und_frames: dict[str, pd.DataFrame] = {}
    try:
        from app.services.borsapy_client import fetch_ohlcv_batch_borsapy

        und_frames.update(fetch_ohlcv_batch_borsapy(unique_und, timeframe, on_progress=on_progress))
    except Exception as exc:
        logger.warning("VIOP borsapy batch failed: %s", exc)

    missing = [u for u in unique_und if u not in und_frames]
    if missing:
        from app.services.batch_data import fetch_yfinance_ohlcv_batch

        extra = fetch_yfinance_ohlcv_batch(
            missing,
            timeframe,
            "bist",
            on_progress=on_progress,
            progress_offset=len(und_frames),
            progress_total=len(unique_und),
        )
        und_frames.update(extra)

    out: dict[str, pd.DataFrame] = {}
    for und, codes in by_und.items():
        frame = und_frames.get(und)
        if frame is None:
            continue
        for code in codes:
            out[code] = frame.copy()

    logger.info("VIOP OHLCV %d / %d (dayanak serisi)", len(out), len(clean))
    return out
