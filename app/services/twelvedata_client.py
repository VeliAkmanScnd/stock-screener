"""Twelve Data API client for Borsa İstanbul (BIST)."""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx
import pandas as pd

from app.config import TWELVE_DATA_API_KEY, TWELVE_DATA_BASE_URL
from app.services.batch_data import RESAMPLED_TIMEFRAMES, _resample_ohlcv
from app.services.ticker_format import clean_bist_symbol

logger = logging.getLogger(__name__)

BIST_EXCHANGE = "BIST"
OHLCV_COLS = ["Open", "High", "Low", "Close", "Volume"]

INTERVAL_MAP: dict[str, str] = {
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "1h": "1h",
    "4h": "1h",
    "8h": "1h",
    "12h": "1h",
    "1d": "1day",
    "1wk": "1week",
    "1mo": "1month",
}

OUTPUTSIZE: dict[str, int] = {
    "5m": 500,
    "15m": 1500,
    "30m": 2000,
    "1h": 5000,
    "4h": 5000,
    "8h": 5000,
    "12h": 5000,
    "1d": 500,
    "1wk": 260,
    "1mo": 120,
}

MIN_BARS: dict[str, int] = {
    "5m": 55,
    "15m": 55,
    "30m": 55,
    "1h": 55,
    "4h": 55,
    "8h": 55,
    "12h": 55,
    "1d": 30,
    "1wk": 30,
    "1mo": 30,
}

# Free plan ~8 requests/min — throttle to avoid 429
_RATE_LOCK = threading.Lock()
_LAST_REQUEST_AT = 0.0
_MIN_REQUEST_INTERVAL = 7.5
_MAX_WORKERS = 2


class TwelveDataError(Exception):
    pass


def is_configured() -> bool:
    return bool(TWELVE_DATA_API_KEY)


def require_api_key() -> str:
    if not TWELVE_DATA_API_KEY:
        raise TwelveDataError(
            "BIST verisi için Twelve Data API anahtarı gerekli. "
            "Ücretsiz anahtar: https://twelvedata.com/apikey — "
            "projeye .env dosyasına TWELVE_DATA_API_KEY=... ekleyin."
        )
    return TWELVE_DATA_API_KEY


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=TWELVE_DATA_BASE_URL,
        timeout=90.0,
        follow_redirects=True,
        headers={"User-Agent": "StockScreener/1.0"},
    )


def _throttle() -> None:
    global _LAST_REQUEST_AT
    with _RATE_LOCK:
        now = time.time()
        wait = _MIN_REQUEST_INTERVAL - (now - _LAST_REQUEST_AT)
        if wait > 0:
            time.sleep(wait)
        _LAST_REQUEST_AT = time.time()


def fetch_bist_symbol_list() -> tuple[str, ...]:
    key = require_api_key()
    try:
        with _client() as client:
            response = client.get(
                "/stocks",
                params={"exchange": BIST_EXCHANGE, "apikey": key},
            )
        if response.status_code != 200:
            raise TwelveDataError(f"Twelve Data stocks HTTP {response.status_code}")
        payload = response.json()
    except TwelveDataError:
        raise
    except Exception as exc:
        raise TwelveDataError(f"BIST sembol listesi alınamadı: {exc}") from exc

    if payload.get("status") == "error":
        raise TwelveDataError(payload.get("message", "Twelve Data stocks error"))

    syms: list[str] = []
    for row in payload.get("data") or []:
        if (row.get("exchange") or "").upper() != BIST_EXCHANGE:
            continue
        if (row.get("type") or "").lower() != "common stock":
            continue
        code = clean_bist_symbol(row.get("symbol") or "")
        if code and len(code) <= 6:
            syms.append(code)

    out = tuple(sorted(set(syms)))
    if len(out) < 100:
        raise TwelveDataError(f"BIST sembol listesi eksik ({len(out)})")
    logger.info("BIST symbols from Twelve Data: %d", len(out))
    return out


def _parse_time_series(payload: dict) -> pd.DataFrame | None:
    if not payload or payload.get("status") == "error":
        return None
    values = payload.get("values") or []
    if not values:
        return None

    rows = []
    for v in values:
        try:
            rows.append(
                {
                    "datetime": v["datetime"],
                    "Open": float(v["open"]),
                    "High": float(v["high"]),
                    "Low": float(v["low"]),
                    "Close": float(v["close"]),
                    "Volume": float(v.get("volume") or 0),
                }
            )
        except (KeyError, TypeError, ValueError):
            continue

    if not rows:
        return None

    df = pd.DataFrame(rows)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.set_index("datetime").sort_index()
    return df[OHLCV_COLS]


def fetch_time_series(symbol: str, timeframe: str) -> pd.DataFrame | None:
    """Single symbol — never raises; returns None on missing/invalid data."""
    key = require_api_key()
    sym = clean_bist_symbol(symbol)
    td_interval = INTERVAL_MAP.get(timeframe, "1day")
    outputsize = OUTPUTSIZE.get(timeframe, 500)
    min_bars = MIN_BARS.get(timeframe, 30)

    params = {
        "symbol": sym,
        "exchange": BIST_EXCHANGE,
        "interval": td_interval,
        "outputsize": outputsize,
        "apikey": key,
    }

    for attempt in range(2):
        try:
            _throttle()
            with _client() as client:
                response = client.get("/time_series", params=params)

            if response.status_code == 429:
                logger.warning("Twelve Data rate limit, waiting 60s…")
                time.sleep(60)
                continue

            if response.status_code != 200:
                return None

            payload = response.json()
            if payload.get("status") == "error":
                return None

            df = _parse_time_series(payload)
            if df is None:
                return None

            resample_rule = RESAMPLED_TIMEFRAMES.get(timeframe)
            if resample_rule:
                df = _resample_ohlcv(df, resample_rule)

            return df if df is not None and len(df) >= min_bars else None
        except Exception as exc:
            logger.debug("Twelve Data %s: %s", sym, exc)
            return None

    return None


def fetch_ohlcv_batch_bist(symbols: list[str], timeframe: str) -> dict[str, pd.DataFrame]:
    """Download BIST OHLCV per symbol (rate-limited, fault-tolerant)."""
    require_api_key()
    if not symbols:
        return {}

    all_frames: dict[str, pd.DataFrame] = {}
    clean_syms = [clean_bist_symbol(s) for s in symbols if clean_bist_symbol(s)]

    workers = min(_MAX_WORKERS, max(1, len(clean_syms)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_time_series, sym, timeframe): sym for sym in clean_syms}
        for fut in as_completed(futures):
            sym = futures[fut]
            try:
                df = fut.result()
                if df is not None:
                    all_frames[sym] = df
            except Exception as exc:
                logger.debug("BIST batch item %s failed: %s", sym, exc)

    logger.info("BIST downloaded %d / %d symbols", len(all_frames), len(clean_syms))
    return all_frames


def fetch_market_cap(symbol: str) -> float | None:
    key = require_api_key()
    sym = clean_bist_symbol(symbol)
    try:
        _throttle()
        with _client() as client:
            response = client.get(
                "/market_cap",
                params={"symbol": sym, "exchange": BIST_EXCHANGE, "apikey": key},
            )
        if response.status_code != 200:
            return None
        payload = response.json()
        if payload.get("status") == "error":
            return None
        val = payload.get("market_cap") or (payload.get("data") or {}).get("market_cap")
        return float(val) if val else None
    except Exception:
        return None
