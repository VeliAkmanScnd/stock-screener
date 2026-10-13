"""Disk cache for OHLCV bars.

Full history is stored per symbol. Later scans reuse it and download only a
short recent window, then splice that window onto the stored bars.
"""

from __future__ import annotations

import logging
import pickle
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import quote

import pandas as pd

from app.config import STORAGE_DIR

logger = logging.getLogger(__name__)

OHLCV_COLS = ["Open", "High", "Low", "Close", "Volume"]
MAX_BARS = 20000
# A second click in the same minute should not hit the network again.
FRESH_WITHIN = timedelta(minutes=3)

# (yahoo/borsapy period, max age of the last stored bar before a full refetch)
_TAIL: dict[str, tuple[str, timedelta]] = {
    "3m": ("5d", timedelta(days=3)),
    "5m": ("5d", timedelta(days=4)),
    "15m": ("5d", timedelta(days=4)),
    "30m": ("5d", timedelta(days=4)),
    "1h": ("5d", timedelta(days=4)),
    "2h": ("1mo", timedelta(days=25)),
    "4h": ("1mo", timedelta(days=25)),
    "8h": ("3mo", timedelta(days=70)),
    "12h": ("3mo", timedelta(days=70)),
    "1d": ("3mo", timedelta(days=80)),
    "1wk": ("1y", timedelta(days=300)),
    "1mo": ("2y", timedelta(days=500)),
}

_SAFE = re.compile(r"[^A-Za-z0-9_.-]+")


def _root() -> Path:
    path = STORAGE_DIR / "ohlcv"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _path(namespace: str, timeframe: str, symbol: str) -> Path:
    folder = _root() / _SAFE.sub("_", namespace) / _SAFE.sub("_", timeframe)
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{quote(symbol, safe='')}.pkl"


def _naive_index(df: pd.DataFrame | None) -> pd.DataFrame | None:
    if df is None or df.empty:
        return None
    work = df.copy()
    if isinstance(work.columns, pd.MultiIndex):
        return None
    work = work.rename(columns=str.title)
    if not set(OHLCV_COLS).issubset(work.columns):
        return None
    work = work[OHLCV_COLS]
    if getattr(work.index, "tz", None) is not None:
        work.index = work.index.tz_localize(None)
    work = work[~work.index.duplicated(keep="last")].sort_index()
    return work if not work.empty else None


def merge_tail(old: pd.DataFrame | None, new: pd.DataFrame | None) -> pd.DataFrame | None:
    """Keep history older than the fresh download. The download replaces its own span.

    A bar inside that span is overwritten, so a 15m close that was stored from
    an unfinished 5m slice is corrected once the window's last 5m bar arrives.
    A stored bar after the fresh series ends is dropped: the resample left it
    out because that bucket is still missing its final source bar.
    """
    new_n = _naive_index(new)
    old_n = _naive_index(old)
    if new_n is None:
        return old_n
    if old_n is None or old_n.empty:
        out = new_n
    else:
        start = new_n.index[0]
        end = new_n.index[-1]
        older = old_n[old_n.index < start]
        missed = old_n[
            (old_n.index > start)
            & (old_n.index < end)
            & ~old_n.index.isin(new_n.index)
        ]
        out = pd.concat([older, missed, new_n])
        out = out[~out.index.duplicated(keep="last")].sort_index()
    if len(out) > MAX_BARS:
        out = out.iloc[-MAX_BARS:]
    return out


def _load(namespace: str, timeframe: str, symbol: str) -> tuple[datetime, pd.DataFrame] | None:
    path = _path(namespace, timeframe, symbol)
    if not path.is_file():
        return None
    try:
        with path.open("rb") as fh:
            fetched_at, frame = pickle.load(fh)
        frame_n = _naive_index(frame)
        if frame_n is None or not isinstance(fetched_at, datetime):
            return None
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        return fetched_at, frame_n
    except Exception:
        logger.warning("OHLCV cache unreadable: %s", path.name)
        return None


def _save(namespace: str, timeframe: str, symbol: str, frame: pd.DataFrame) -> None:
    frame_n = _naive_index(frame)
    if frame_n is None or frame_n.empty:
        return
    path = _path(namespace, timeframe, symbol)
    payload = (datetime.now(timezone.utc), frame_n)
    tmp = path.with_suffix(".tmp")
    with tmp.open("wb") as fh:
        pickle.dump(payload, fh, protocol=pickle.HIGHEST_PROTOCOL)
    tmp.replace(path)


def _last_gap(frame: pd.DataFrame) -> timedelta | None:
    last = pd.Timestamp(frame.index[-1])
    if last.tzinfo is not None:
        last = last.tz_convert("UTC").tz_localize(None)
    now = pd.Timestamp.now(tz="UTC").tz_localize(None)
    return now - last


def tail_spec(timeframe: str) -> tuple[str, timedelta]:
    return _TAIL.get(timeframe, ("1mo", timedelta(days=25)))


def fetched_after_bar_close(
    frame: pd.DataFrame,
    fetched_at: datetime,
    timeframe: str,
) -> bool:
    """False when the last bar was still open (or inside the settle gap) at fetch time.

    BIST/VIOP caches store Istanbul-naive timestamps. A frame saved at 10:12
    whose last bar is the 10:00–10:15 candle still has the live print as Close.
    Reusing it after 10:15 signals that print.
    """
    from app.services.bar_close import BAR_SETTLE_SECONDS, TIMEFRAME_SECONDS

    secs = TIMEFRAME_SECONDS.get((timeframe or "").strip().lower())
    if not secs or secs >= 86400 or frame is None or frame.empty:
        return True
    last = pd.Timestamp(frame.index[-1])
    if last.tzinfo is not None:
        last = last.tz_convert("Europe/Istanbul").tz_localize(None)
    close_at = last + pd.Timedelta(seconds=secs + BAR_SETTLE_SECONDS)
    fetched = pd.Timestamp(fetched_at)
    if fetched.tzinfo is None:
        fetched = fetched.tz_localize("UTC")
    fetched = fetched.tz_convert("Europe/Istanbul").tz_localize(None)
    return bool(fetched >= close_at)


def cached_ohlcv_batch(
    *,
    namespace: str,
    timeframe: str,
    symbols: list[str],
    min_bars: int,
    full_period: str,
    fetch_period: Callable[[list[str], str, int, int], dict[str, pd.DataFrame]],
    on_progress: Callable[[int, int, str], None] | None = None,
    progress_offset: int = 0,
    progress_total: int | None = None,
) -> dict[str, pd.DataFrame]:
    """Return frames, downloading a short tail when history is already stored."""
    if not symbols:
        return {}

    total = progress_total if progress_total is not None else progress_offset + len(symbols)
    done = progress_offset
    tail_period, coverage = tail_spec(timeframe)
    now = datetime.now(timezone.utc)

    base: dict[str, pd.DataFrame] = {}
    tail: list[str] = []
    full: list[str] = []
    fresh_n = 0
    for sym in symbols:
        loaded = _load(namespace, timeframe, sym)
        if loaded is None or len(loaded[1]) < min_bars:
            full.append(sym)
            continue
        fetched_at, frame = loaded
        if now - fetched_at <= FRESH_WITHIN and (
            not (namespace.startswith("bp_") or namespace.startswith("yf_fx"))
            or fetched_after_bar_close(frame, fetched_at, timeframe)
        ):
            base[sym] = frame
            fresh_n += 1
            continue
        gap = _last_gap(frame)
        if gap is None or gap > coverage:
            full.append(sym)
        else:
            tail.append(sym)
            base[sym] = frame

    if fresh_n and on_progress:
        done += fresh_n
        on_progress(min(done, total), total, "önbellek")

    logger.info(
        "OHLCV %s %s: %d cached, %d tail, %d full",
        namespace,
        timeframe,
        fresh_n,
        len(tail),
        len(full),
    )

    out = dict(base)

    def _take(batch: list[str], period: str, *, replace: bool) -> None:
        nonlocal done
        if not batch:
            return
        got = fetch_period(batch, period, done, total)
        for sym, frame in got.items():
            if replace:
                merged = _naive_index(frame)
            else:
                merged = merge_tail(out.get(sym), frame)
            if merged is None or len(merged) < min_bars:
                continue
            _save(namespace, timeframe, sym, merged)
            out[sym] = merged
        done += len(batch)

    _take(full, full_period, replace=True)
    _take(tail, tail_period, replace=False)
    return {s: f for s, f in out.items() if len(f) >= min_bars}
