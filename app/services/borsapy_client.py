"""borsapy batch OHLCV for BIST (optional TradingView live via session cookies)."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

import pandas as pd

from app.config import TRADINGVIEW_SESSION_ID, TRADINGVIEW_SESSION_SIGN
from app.services.batch_data import RESAMPLED_SOURCE_PERIOD, RESAMPLED_TIMEFRAMES, _resample_ohlcv
from app.services.data_fetcher import INTRADAY_MIN_BARS, INTRADAY_PERIOD, INTRADAY_TIMEFRAMES
from app.services.ticker_format import clean_bist_symbol

logger = logging.getLogger(__name__)

OHLCV_COLS = ["Open", "High", "Low", "Close", "Volume"]
BORSA_PY_CHUNK_SIZE = 25
BORSA_PY_WORKERS = 4
# 15m/30m are built from 5m. 40 calendar days is enough for the strong-fresh
# lookback and is much smaller than a 60d cold download of the whole board.
_RESAMPLE_SOURCE_PERIOD = "40d"
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
        import inspect

        import borsapy as bp

        params = inspect.signature(bp.set_tradingview_auth).parameters
        kwargs = {}
        if "session" in params:
            kwargs["session"] = TRADINGVIEW_SESSION_ID
        elif "session_id" in params:
            kwargs["session_id"] = TRADINGVIEW_SESSION_ID
        if "session_sign" in params:
            kwargs["session_sign"] = TRADINGVIEW_SESSION_SIGN
        bp.set_tradingview_auth(**kwargs)
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
        level0 = {str(x) for x in data.columns.get_level_values(0)}
        for sym in symbols:
            code = clean_bist_symbol(sym) or str(sym).strip()
            want_continuous = code.endswith("1!")
            aliases = [code, str(sym).strip()]
            if want_continuous:
                # Never match cash dayanak (TOASO) when requesting TOASO1!
                aliases.append(code.upper())
            else:
                aliases.extend(
                    [
                        code.replace("1!", ""),
                        f"{code}1!" if not code.endswith("1!") else code,
                    ]
                )
            hit = next((a for a in aliases if a and a in level0), None)
            if not hit:
                # Case-insensitive continuous match
                if want_continuous:
                    hit = next(
                        (a for a in level0 if str(a).upper() == code.upper()),
                        None,
                    )
            if not hit:
                continue
            try:
                sub = data.xs(hit, axis=1, level=0, drop_level=True)
                frame = _normalize_frame(sub)
                if frame is not None:
                    out[code] = frame
            except (KeyError, ValueError):
                continue
    else:
        frame = _normalize_frame(data)
        if frame is not None and len(symbols) == 1:
            key = clean_bist_symbol(symbols[0]) or str(symbols[0]).strip()
            out[key] = frame
    return out


def _period_interval(timeframe: str) -> tuple[str, str, str | None]:
    """Return (period, download interval, resample rule or None).

    Native 15m and 30m bars from borsapy can drop a wick that the 5m series
    still has. OZKGY 2026-10-08 10:00 is high 12.01 on 15m and 12.08 on 5m,
    which is the strong high on the chart. Build those bars from 5m.
    """
    resample_rule = RESAMPLED_TIMEFRAMES.get(timeframe)
    if resample_rule:
        return RESAMPLED_SOURCE_PERIOD, "1h", resample_rule
    if timeframe == "15m":
        return _RESAMPLE_SOURCE_PERIOD, "5m", "15min"
    if timeframe == "30m":
        return _RESAMPLE_SOURCE_PERIOD, "5m", "30min"
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
    min_bars = INTRADAY_MIN_BARS if timeframe in INTRADAY_TIMEFRAMES or resample_rule else 30
    namespace = (
        "bp_viop"
        if clean_syms and all(s.endswith("1!") for s in clean_syms)
        else "bp_bist"
    )
    # Don't reuse 15m/30m files built from the native feed; those highs are short.
    if interval == "5m" and timeframe in ("15m", "30m"):
        namespace = f"{namespace}_m5"

    wait = 0.0
    if timeframe in INTRADAY_TIMEFRAMES or resample_rule:
        from app.services.bar_close import seconds_until_bar_settled

        wait = seconds_until_bar_settled(timeframe)
    if wait > 0:
        logger.info("Waiting %.0fs for the %s bar to settle", wait, timeframe)
        time.sleep(wait)
    asof = pd.Timestamp.now(tz="Europe/Istanbul")

    def _download_chunk(chunk: list[str], use_period: str) -> dict[str, pd.DataFrame]:
        raw = bp.download(
            chunk,
            period=use_period,
            interval=interval,
            group_by="ticker",
            progress=False,
        )
        chunk_frames = _split_download(raw, chunk)
        if not resample_rule:
            return chunk_frames
        out: dict[str, pd.DataFrame] = {}
        for sym, frame in chunk_frames.items():
            resampled = _resample_ohlcv(frame, resample_rule, asof=asof)
            if resampled is not None:
                out[sym] = resampled
        return out

    def fetch_period(
        batch: list[str],
        use_period: str,
        offset: int,
        total: int,
    ) -> dict[str, pd.DataFrame]:
        chunks = [
            batch[i : i + BORSA_PY_CHUNK_SIZE]
            for i in range(0, len(batch), BORSA_PY_CHUNK_SIZE)
        ]
        frames: dict[str, pd.DataFrame] = {}
        if not chunks:
            return frames
        done = offset
        workers = 1 if len(chunks) == 1 else min(BORSA_PY_WORKERS, len(chunks))

        def _one(chunk: list[str]) -> tuple[list[str], dict[str, pd.DataFrame], Exception | None]:
            try:
                return chunk, _download_chunk(chunk, use_period), None
            except Exception as exc:
                return chunk, {}, exc

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_one, chunk) for chunk in chunks]
            for fut in as_completed(futures):
                chunk, built, exc = fut.result()
                if exc is not None:
                    logger.warning("borsapy chunk failed (%s): %s", chunk[:3], exc)
                else:
                    frames.update(built)
                done += len(chunk)
                if on_progress:
                    label = chunk[-1] if chunk else ""
                    on_progress(min(done, total), total, label)
        return frames

    from app.services.ohlcv_store import cached_ohlcv_batch

    return cached_ohlcv_batch(
        namespace=namespace,
        timeframe=timeframe,
        symbols=clean_syms,
        min_bars=min_bars,
        full_period=period,
        fetch_period=fetch_period,
        on_progress=on_progress,
        progress_offset=progress_offset,
        progress_total=progress_total,
    )
