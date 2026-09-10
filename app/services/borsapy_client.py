"""borsapy batch OHLCV for BIST (optional TradingView live via session cookies)."""

from __future__ import annotations

import logging
from typing import Callable

import pandas as pd

from app.config import TRADINGVIEW_SESSION_ID, TRADINGVIEW_SESSION_SIGN
from app.services.batch_data import RESAMPLED_SOURCE_PERIOD, RESAMPLED_TIMEFRAMES, _resample_ohlcv
from app.services.data_fetcher import INTRADAY_MIN_BARS, INTRADAY_PERIOD, INTRADAY_TIMEFRAMES
from app.services.ticker_format import clean_bist_symbol

logger = logging.getLogger(__name__)

OHLCV_COLS = ["Open", "High", "Low", "Close", "Volume"]
BORSA_PY_CHUNK_SIZE = 25
_tv_auth_applied = False


def is_borsapy_available() -> bool:
    try:
        import borsapy  # noqa: F401

        return True
    except ImportError:
        return False


def tradingview_auth_configured() -> bool:
    return bool(TRADINGVIEW_SESSION_ID and TRADINGVIEW_SESSION_SIGN)


def ensure_tradingview_auth() -> bool:
    """Apply TV session cookies once per process (enables live BIST on borsapy)."""
    global _tv_auth_applied
    if _tv_auth_applied or not tradingview_auth_configured():
        return tradingview_auth_configured()
    try:
        import borsapy as bp

        bp.set_tradingview_auth(
            session_id=TRADINGVIEW_SESSION_ID,
            session_sign=TRADINGVIEW_SESSION_SIGN,
        )
        _tv_auth_applied = True
        logger.info("borsapy TradingView auth applied (live BIST if subscribed)")
        return True
    except Exception as exc:
        logger.warning("borsapy TradingView auth failed: %s", exc)
        return False


def _normalize_frame(df: pd.DataFrame) -> pd.DataFrame | None:
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        return None
    work = df.rename(columns=str.title)
    if not set(OHLCV_COLS).issubset(work.columns):
        return None
    out = work[OHLCV_COLS].dropna(how="all")
    if work.index.tz is not None:
        out = out.copy()
        out.index = out.index.tz_localize(None)
    return out if len(out) >= 10 else None


def _split_download(data: pd.DataFrame, symbols: list[str]) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    if data is None or data.empty:
        return out

    if isinstance(data.columns, pd.MultiIndex):
        for sym in symbols:
            code = clean_bist_symbol(sym)
            try:
                sub = data.xs(code, axis=1, level=0, drop_level=True)
                frame = _normalize_frame(sub)
                if frame is not None:
                    out[code] = frame
            except (KeyError, ValueError):
                continue
    else:
        frame = _normalize_frame(data)
        if frame is not None and len(symbols) == 1:
            out[clean_bist_symbol(symbols[0])] = frame
    return out


def _period_interval(timeframe: str) -> tuple[str, str, int | None]:
    """Return (period, interval, resample_rule or None)."""
    resample_rule = RESAMPLED_TIMEFRAMES.get(timeframe)
    if resample_rule:
        return RESAMPLED_SOURCE_PERIOD, "1h", resample_rule
    if timeframe in INTRADAY_TIMEFRAMES:
        return INTRADAY_PERIOD, timeframe, None
    if timeframe == "1d":
        return "1y", "1d", None
    if timeframe == "1wk":
        return "2y", "1wk", None
    if timeframe == "1mo":
        return "5y", "1mo", None
    return INTRADAY_PERIOD, timeframe, None


def fetch_ohlcv_batch_borsapy(
    symbols: list[str],
    timeframe: str,
    on_progress: Callable[[int, int, str], None] | None = None,
    progress_offset: int = 0,
    progress_total: int | None = None,
) -> dict[str, pd.DataFrame]:
    if not is_borsapy_available():
        raise ImportError("borsapy yüklü değil — pip install borsapy")

    import borsapy as bp

    ensure_tradingview_auth()

    clean_syms = [clean_bist_symbol(s) for s in symbols if clean_bist_symbol(s)]
    if not clean_syms:
        return {}

    period, interval, resample_rule = _period_interval(timeframe)
    all_frames: dict[str, pd.DataFrame] = {}
    total = progress_total if progress_total is not None else len(clean_syms)
    done = progress_offset

    for i in range(0, len(clean_syms), BORSA_PY_CHUNK_SIZE):
        chunk = clean_syms[i : i + BORSA_PY_CHUNK_SIZE]
        try:
            raw = bp.download(
                chunk,
                period=period,
                interval=interval,
                group_by="ticker",
                progress=False,
            )
            chunk_frames = _split_download(raw, chunk)
            if resample_rule:
                for sym, frame in chunk_frames.items():
                    resampled = _resample_ohlcv(frame, resample_rule)
                    if resampled is not None:
                        all_frames[sym] = resampled
            else:
                all_frames.update(chunk_frames)
        except Exception as exc:
            logger.warning("borsapy chunk failed (%s): %s", chunk[:3], exc)

        done += len(chunk)
        if on_progress:
            label = chunk[-1] if chunk else ""
            on_progress(min(done, total), total, label)

    min_bars = INTRADAY_MIN_BARS if timeframe in INTRADAY_TIMEFRAMES or resample_rule else 30
    return {s: f for s, f in all_frames.items() if len(f) >= min_bars}
