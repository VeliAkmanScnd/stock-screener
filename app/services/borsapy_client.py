"""borsapy batch OHLCV for BIST (optional TradingView live via session cookies)."""

from __future__ import annotations

import logging
import threading
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
# One symbol per task so a finished contract can be scanned immediately.
# Four sockets is the rate TradingView accepts; a fifth handshake returns 429.
BORSA_PY_CHUNK_SIZE = 1
BORSA_PY_WORKERS = 4
_TV_SLOTS = threading.Semaphore(BORSA_PY_WORKERS)
_flight_lock = threading.Lock()
_flights: dict[tuple, dict] = {}
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
    on_frames: Callable[[dict[str, pd.DataFrame]], None] | None = None,
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
        with _TV_SLOTS:
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
        on_chunk: Callable[[dict[str, pd.DataFrame]], None] | None = None,
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
                elif built:
                    frames.update(built)
                    if on_chunk:
                        try:
                            on_chunk(built)
                        except Exception:
                            logger.exception("OHLCV chunk callback failed")
                done += len(chunk)
                if on_progress:
                    label = chunk[-1] if chunk else ""
                    on_progress(min(done, total), total, label)
        return frames

    from app.services.ohlcv_store import cached_ohlcv_batch

    flight_key = (namespace, timeframe, tuple(sorted(clean_syms)))
    with _flight_lock:
        flight = _flights.get(flight_key)
        if flight is None:
            flight = {"event": threading.Event(), "box": {}}
            _flights[flight_key] = flight
            leader = True
        else:
            leader = False
    if not leader:
        flight["event"].wait()
        if flight["box"].get("error") is not None:
            raise flight["box"]["error"]
        frames = flight["box"].get("frames") or {}
        return {sym: frame.copy() for sym, frame in frames.items()}

    try:
        frames = cached_ohlcv_batch(
            namespace=namespace,
            timeframe=timeframe,
            symbols=clean_syms,
            min_bars=min_bars,
            full_period=period,
            fetch_period=fetch_period,
            on_progress=on_progress,
            progress_offset=progress_offset,
            progress_total=progress_total,
            on_frames=on_frames,
        )
        flight["box"]["frames"] = frames
        return frames
    except Exception as exc:
        flight["box"]["error"] = exc
        raise
    finally:
        flight["event"].set()
        with _flight_lock:
            _flights.pop(flight_key, None)


BACKTEST_PERIODS: dict[str, tuple[int, str]] = {
    # ui value -> (target calendar days, borsapy period)
    "40d": (40, "90d"),
    "60d": (60, "90d"),
    "90d": (90, "3mo"),
    "6mo": (183, "6mo"),
    "8mo": (244, "1y"),
    "13mo": (400, "2y"),
    "2y": (730, "2y"),
}


def backtest_period_days(period: str) -> int:
    if period in BACKTEST_PERIODS:
        return BACKTEST_PERIODS[period][0]
    return 60


def _borsapy_backtest_period(period: str) -> str:
    if period in BACKTEST_PERIODS:
        return BACKTEST_PERIODS[period][1]
    return period or "90d"


def _frame_span_days(df: pd.DataFrame) -> int:
    if df is None or df.empty:
        return 0
    start = df.index[0]
    end = df.index[-1]
    try:
        return max(0, int((end - start).days))
    except Exception:
        return 0


def coverage_note(timeframe: str, period: str, span_days: int) -> str:
    want = backtest_period_days(period)
    if span_days >= int(want * 0.7):
        return ""
    if timeframe == "5m":
        return "5m TradingView indirme bu turda istenen süreden kısa geldi."
    if timeframe == "15m":
        return "15m parça indirme TV grafiğindeki kadar gelmedi; tekrar deneyin."
    if timeframe == "30m":
        return "30m TradingView indirme istenen süreden kısa geldi."
    return f"İstenen süre {want} gün, gelen veri {span_days} gün."


# One TV history call is bar-capped (~5–10k). 15m VIOP ~32 bars/day → ~8 months
# in a single shot. Page backward with start/end so tester matches the TV chart.
_CHUNK_CALENDAR_DAYS = {
    "1m": 7,
    "3m": 35,
    "5m": 50,
    "15m": 140,
    "30m": 260,
    "1h": 400,
}
_CHUNK_OVERLAP_DAYS = 3


def backtest_chunk_windows(
    start: pd.Timestamp,
    end: pd.Timestamp,
    chunk_days: int,
    overlap_days: int = _CHUNK_OVERLAP_DAYS,
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Newest-first windows covering [start, end]."""
    if end <= start or chunk_days <= 0:
        return [(start, end)] if end > start else []
    windows: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    cursor = pd.Timestamp(end)
    floor = pd.Timestamp(start)
    overlap = pd.Timedelta(days=max(0, overlap_days))
    guard = 0
    while cursor > floor and guard < 40:
        guard += 1
        w_end = cursor
        w_start = max(floor, w_end - pd.Timedelta(days=chunk_days))
        windows.append((w_start, w_end))
        if w_start <= floor:
            break
        cursor = w_start + overlap
        if cursor >= w_end:
            cursor = w_start
    return windows


def merge_ohlcv_parts(parts: list[pd.DataFrame]) -> pd.DataFrame | None:
    frames = [p for p in parts if p is not None and not p.empty]
    if not frames:
        return None
    out = pd.concat(frames)
    out = out[~out.index.duplicated(keep="last")].sort_index()
    return None if out.empty else out


def _backtest_attempts(timeframe: str, want_days: int) -> list[tuple[str, str | None]]:
    """Prefer 5m→15m/30m wicks for short windows; native bars for long history."""
    if timeframe == "15m":
        if want_days <= 75:
            return [("5m", "15min"), ("15m", None)]
        return [("15m", None)]
    if timeframe == "30m":
        if want_days <= 75:
            return [("5m", "30min"), ("30m", None)]
        return [("30m", None)]
    if timeframe == "1h":
        return [("1h", None)]
    if timeframe == "1d":
        return [("1d", None)]
    if timeframe == "5m":
        return [("5m", None)]
    return [(timeframe, None)]


def fetch_ohlcv_one_backtest(
    symbol: str,
    timeframe: str,
    period: str = "60d",
) -> pd.DataFrame | None:
    """Single-symbol TradingView OHLCV for optimizer (no live settle wait)."""
    if not is_borsapy_available():
        raise ImportError("borsapy yüklü değil — pip install borsapy")

    import borsapy as bp

    from app.services.ticker_format import to_viop_continuous_symbol

    ensure_tradingview_auth()
    raw = str(symbol or "").strip()
    if not raw:
        return None

    candidates: list[str] = []
    cont = to_viop_continuous_symbol(raw)
    if cont.endswith("1!"):
        candidates.append(cont)
    cash = clean_bist_symbol(raw)
    if cash and cash not in candidates and not cash.endswith("1!"):
        candidates.append(cash)
    if not candidates:
        candidates.append(raw.upper())

    want_days = backtest_period_days(period)
    bp_period = _borsapy_backtest_period(period)
    attempts = _backtest_attempts(timeframe, want_days)
    asof = pd.Timestamp.now(tz="Europe/Istanbul")
    asof_naive = pd.Timestamp(asof)
    if asof_naive.tzinfo is not None:
        asof_naive = asof_naive.tz_convert("Europe/Istanbul").tz_localize(None)
    end = asof_naive.normalize() + pd.Timedelta(days=1)
    start = end - pd.Timedelta(days=want_days)
    last_error: Exception | None = None
    best: pd.DataFrame | None = None
    best_span = -1

    def _one_shot(ticker: str, interval: str, *, period_key: str | None = None, start_at=None, end_at=None):
        kwargs: dict = {
            "tickers": [ticker],
            "interval": interval,
            "group_by": "ticker",
            "progress": False,
        }
        if start_at is not None:
            kwargs["start"] = pd.Timestamp(start_at).strftime("%Y-%m-%d")
            kwargs["end"] = pd.Timestamp(end_at or end).strftime("%Y-%m-%d")
        else:
            kwargs["period"] = period_key or bp_period
        with _TV_SLOTS:
            raw_df = bp.download(**kwargs)
        frames = _split_download(raw_df, [ticker])
        frame = frames.get(ticker)
        if frame is None and frames:
            frame = next(iter(frames.values()))
        return frame

    def _chunked(ticker: str, interval: str):
        chunk_days = _CHUNK_CALENDAR_DAYS.get(interval, 0)
        if chunk_days <= 0 or want_days <= chunk_days:
            return _one_shot(ticker, interval, start_at=start, end_at=end)
        parts: list[pd.DataFrame] = []
        oldest_seen: pd.Timestamp | None = None
        for w_start, w_end in backtest_chunk_windows(start, end, chunk_days):
            piece = _one_shot(ticker, interval, start_at=w_start, end_at=w_end)
            if piece is None or piece.empty:
                if parts:
                    break
                continue
            parts.append(piece)
            piece_oldest = pd.Timestamp(piece.index.min())
            if oldest_seen is not None and piece_oldest >= oldest_seen - pd.Timedelta(days=2):
                break
            oldest_seen = piece_oldest if oldest_seen is None else min(oldest_seen, piece_oldest)
            if oldest_seen <= start + pd.Timedelta(days=2):
                break
            time.sleep(0.15)
        merged = merge_ohlcv_parts(parts)
        if merged is not None:
            return merged
        return _one_shot(ticker, interval, period_key=bp_period)

    for ticker in candidates:
        for interval, resample_rule in attempts:
            try:
                if resample_rule:
                    frame = _one_shot(ticker, interval, period_key=bp_period)
                    if frame is not None:
                        frame = _resample_ohlcv(frame, resample_rule, asof=asof)
                else:
                    frame = _chunked(ticker, interval)
                norm = _normalize_frame(frame) if frame is not None else None
                if norm is None or len(norm) < 30:
                    continue
                span = _frame_span_days(norm)
                # Short windows: keep 5m-resampled bars when they cover the ask.
                if resample_rule and span >= min(want_days, 35):
                    return norm
                if span > best_span:
                    best = norm
                    best_span = span
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "backtest download %s %s %s failed: %s",
                    ticker,
                    timeframe,
                    interval,
                    exc,
                )
        if best is not None and best_span >= min(want_days, 35):
            return best
    if best is not None:
        return best
    if last_error:
        logger.warning("backtest OHLCV empty for %s: %s", raw, last_error)
    return None
