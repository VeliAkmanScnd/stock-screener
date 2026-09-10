"""BIST OHLCV — Yahoo, borsapy, or Twelve Data (selectable per scan)."""

from __future__ import annotations

import logging
import time
from typing import Callable

import pandas as pd

from app.config import BIST_CACHE_TTL_SECONDS, BIST_DATA_PROVIDER, BIST_TD_FALLBACK
from app.services.batch_data import fetch_yfinance_ohlcv_batch
from app.services.ticker_format import clean_bist_symbol

logger = logging.getLogger(__name__)

DAILY_TIMEFRAMES = frozenset({"1d", "1wk", "1mo"})

BIST_PROVIDER_CHOICES: tuple[tuple[str, str], ...] = (
    ("yfinance", "Yahoo Finance"),
    ("borsapy", "borsapy (İş Yatırım / TV)"),
    ("twelvedata", "Twelve Data"),
    ("auto", "Otomatik"),
)

# (symbol, timeframe) -> (expires_at, dataframe)
_frame_cache: dict[tuple[str, str], tuple[float, pd.DataFrame]] = {}


def normalize_bist_provider(value: str | None) -> str | None:
    if value is None:
        return None
    p = str(value).strip().lower()
    if not p or p in ("default", "env"):
        return None
    aliases = {
        "yahoo": "yfinance",
        "yf": "yfinance",
        "bp": "borsapy",
        "twelve": "twelvedata",
        "td": "twelvedata",
    }
    p = aliases.get(p, p)
    if p not in {x[0] for x in BIST_PROVIDER_CHOICES}:
        return None
    return p


def resolve_bist_provider(timeframe: str, override: str | None = None) -> str:
    p = normalize_bist_provider(override) or (BIST_DATA_PROVIDER or "yfinance").strip().lower()
    p = normalize_bist_provider(p) or "yfinance"

    if p == "yfinance":
        return "yfinance"
    if p == "borsapy":
        return "borsapy"
    if p == "twelvedata":
        return "twelvedata"

    # auto
    if timeframe in DAILY_TIMEFRAMES:
        return "yfinance"
    from app.services.borsapy_client import is_borsapy_available

    if is_borsapy_available():
        return "borsapy"
    from app.services.twelvedata_client import is_configured

    return "twelvedata" if is_configured() else "yfinance"


def active_provider_label(timeframe: str = "1d", override: str | None = None) -> str:
    return resolve_bist_provider(timeframe, override)


def bist_provider_options() -> list[dict[str, str | bool]]:
    from app.services.borsapy_client import is_borsapy_available, tradingview_auth_configured
    from app.services.twelvedata_client import is_configured as td_ok

    hints = {
        "yfinance": "Hızlı toplu indirme (.IS). Ücretsiz, API anahtarı gerekmez.",
        "borsapy": "İş Yatırım + TradingView. Canlı BIST için TV veri paketi + .env cookie.",
        "twelvedata": "Sembol başına yavaş; TWELVE_DATA_API_KEY gerekir.",
        "auto": "Günlük → Yahoo; intraday → borsapy veya Twelve Data.",
    }
    out = []
    for pid, label in BIST_PROVIDER_CHOICES:
        item: dict[str, str | bool] = {
            "id": pid,
            "label": label,
            "hint": hints.get(pid, ""),
            "available": True,
        }
        if pid == "borsapy":
            item["available"] = is_borsapy_available()
        if pid == "twelvedata":
            item["available"] = td_ok()
        out.append(item)
    return out


def bist_scan_ready() -> bool:
    return True


def _cache_get(symbol: str, timeframe: str) -> pd.DataFrame | None:
    key = (clean_bist_symbol(symbol), timeframe)
    row = _frame_cache.get(key)
    if not row:
        return None
    expires_at, df = row
    if time.time() > expires_at:
        _frame_cache.pop(key, None)
        return None
    return df.copy()


def _cache_put(symbol: str, timeframe: str, df: pd.DataFrame) -> None:
    if df is None or df.empty:
        return
    key = (clean_bist_symbol(symbol), timeframe)
    _frame_cache[key] = (time.time() + BIST_CACHE_TTL_SECONDS, df.copy())


def _from_cache(
    symbols: list[str], timeframe: str
) -> tuple[dict[str, pd.DataFrame], list[str]]:
    frames: dict[str, pd.DataFrame] = {}
    missing: list[str] = []
    for sym in symbols:
        code = clean_bist_symbol(sym)
        if not code:
            continue
        cached = _cache_get(code, timeframe)
        if cached is not None:
            frames[code] = cached
        else:
            missing.append(code)
    return frames, missing


def _fetch_twelvedata(
    symbols: list[str],
    timeframe: str,
    on_progress: Callable[[int, int, str], None] | None,
) -> dict[str, pd.DataFrame]:
    from app.services.twelvedata_client import (
        TwelveDataError,
        fetch_ohlcv_batch_bist as td_fetch,
        is_configured,
    )

    if not is_configured():
        raise TwelveDataError(
            "BIST için Twelve Data seçildi ancak TWELVE_DATA_API_KEY tanımlı değil."
        )
    return td_fetch(symbols, timeframe, on_progress=on_progress)


def _fetch_yahoo(
    symbols: list[str],
    timeframe: str,
    on_progress: Callable[[int, int, str], None] | None,
    progress_offset: int,
    progress_total: int,
) -> dict[str, pd.DataFrame]:
    return fetch_yfinance_ohlcv_batch(
        symbols,
        timeframe,
        "bist",
        on_progress=on_progress,
        progress_offset=progress_offset,
        progress_total=progress_total,
    )


def _fetch_borsapy(
    symbols: list[str],
    timeframe: str,
    on_progress: Callable[[int, int, str], None] | None,
    progress_offset: int,
    progress_total: int,
) -> dict[str, pd.DataFrame]:
    from app.services.borsapy_client import fetch_ohlcv_batch_borsapy, is_borsapy_available

    if not is_borsapy_available():
        raise ImportError("borsapy seçildi ancak paket yüklü değil (pip install borsapy)")
    return fetch_ohlcv_batch_borsapy(
        symbols,
        timeframe,
        on_progress=on_progress,
        progress_offset=progress_offset,
        progress_total=progress_total,
    )


def fetch_ohlcv_batch_bist(
    symbols: list[str],
    timeframe: str,
    on_progress: Callable[[int, int, str], None] | None = None,
    provider_override: str | None = None,
) -> dict[str, pd.DataFrame]:
    """Download BIST OHLCV (cached; provider from scan or .env)."""
    clean_syms = [clean_bist_symbol(s) for s in symbols if clean_bist_symbol(s)]
    if not clean_syms:
        return {}

    provider = resolve_bist_provider(timeframe, provider_override)
    frames, missing = _from_cache(clean_syms, timeframe)
    total = len(clean_syms)
    done = len(frames)

    if on_progress and done:
        on_progress(done, total, "önbellek")

    to_fetch = missing if missing else clean_syms

    if provider == "twelvedata":
        fetched = _fetch_twelvedata(to_fetch, timeframe, on_progress)
    elif provider == "borsapy":
        fetched = _fetch_borsapy(to_fetch, timeframe, on_progress, done, total)
    else:
        fetched = _fetch_yahoo(to_fetch, timeframe, on_progress, done, total)

    frames.update(fetched)
    for sym, df in fetched.items():
        _cache_put(sym, timeframe, df)

    if provider == "yfinance" and BIST_TD_FALLBACK and missing:
        still_missing = [s for s in missing if s not in frames]
        if still_missing:
            from app.services.twelvedata_client import is_configured

            if is_configured():
                logger.info(
                    "BIST Yahoo eksik %d sembol — Twelve Data ile tamamlanıyor",
                    len(still_missing),
                )
                try:
                    extra = _fetch_twelvedata(still_missing, timeframe, on_progress)
                    frames.update(extra)
                    for sym, df in extra.items():
                        _cache_put(sym, timeframe, df)
                except Exception as exc:
                    logger.warning("BIST Twelve Data fallback failed: %s", exc)

    logger.info(
        "BIST %s: %d / %d symbols (%s)",
        timeframe,
        len(frames),
        len(clean_syms),
        provider,
    )
    return frames


def fetch_time_series_bist(
    symbol: str,
    timeframe: str,
    provider_override: str | None = None,
) -> pd.DataFrame | None:
    sym = clean_bist_symbol(symbol)
    if not sym:
        return None
    cached = _cache_get(sym, timeframe)
    if cached is not None:
        return cached
    frames = fetch_ohlcv_batch_bist([sym], timeframe, provider_override=provider_override)
    return frames.get(sym)
