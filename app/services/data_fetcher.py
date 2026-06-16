"""Market data and US symbol universes (with HTTP fetch + disk cache)."""

from __future__ import annotations

import csv
import io
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import certifi
import httpx
import pandas as pd
import yfinance as yf

from app.config import BASE_DIR, DEFAULT_LOOKBACK_DAYS, DEFAULT_TIMEFRAME
from app.services.bist_symbols import fetch_bist_symbols_live
from app.services.binance_symbols import fetch_binance_usdt_symbols_live
from app.services.symbol_filter import nasdaq_listed_row_passes, nyse_otherlisted_row_passes
from app.services.ticker_format import clean_bist_symbol, clean_binance_symbol, is_bist_universe, is_binance_universe

logger = logging.getLogger(__name__)

NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
SP500_GITHUB_CSV = (
    "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/master/data/constituents.csv"
)
SP500_WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

CACHE_DIR = BASE_DIR / "storage" / "symbol_cache"
CACHE_TTL = timedelta(hours=24)
# Bump when list filtering logic changes (invalidates old caches)
SYMBOL_CACHE_VERSION = "v2"

INTRADAY_TIMEFRAMES = {"5m", "15m", "30m", "1h"}
INTRADAY_PERIOD = "60d"
INTRADAY_MIN_BARS = 55

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; StockScreener/1.0; +https://github.com/)",
    "Accept": "text/html,application/json,text/plain,*/*",
}


@dataclass
class UniverseMeta:
    ok: bool
    source: str
    message: str | None = None
    cached: bool = False


def _clean_symbol(sym: str) -> str:
    s = str(sym).strip().upper().replace(".", "-")
    if not s or s == "NAN" or len(s) > 10:
        return ""
    return s


def _http_get(url: str) -> str:
    with httpx.Client(
        verify=certifi.where(),
        timeout=90.0,
        follow_redirects=True,
        headers=HTTP_HEADERS,
    ) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.text


def _cache_path(name: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{name}_{SYMBOL_CACHE_VERSION}.json"


def _load_disk_cache(name: str) -> tuple[str, ...] | None:
    path = _cache_path(name)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        symbols = tuple(_clean_symbol(s) for s in payload.get("symbols", []) if _clean_symbol(s))
        return symbols if symbols else None
    except Exception as exc:
        logger.warning("Cache read failed %s: %s", name, exc)
        return None


def _cache_fresh(name: str) -> bool:
    path = _cache_path(name)
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        updated = datetime.fromisoformat(payload["updated"])
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - updated < CACHE_TTL
    except Exception:
        return False


def _save_disk_cache(name: str, symbols: tuple[str, ...], source: str) -> None:
    path = _cache_path(name)
    path.write_text(
        json.dumps(
            {
                "updated": datetime.now(timezone.utc).isoformat(),
                "source": source,
                "symbols": list(symbols),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _resolve_cached(name: str, fetcher, source_label: str) -> tuple[tuple[str, ...], UniverseMeta]:
    if _cache_fresh(name):
        cached = _load_disk_cache(name)
        if cached:
            return cached, UniverseMeta(ok=True, source=source_label, cached=True)

    try:
        symbols = fetcher()
        if not symbols:
            raise ValueError("empty symbol list")
        _save_disk_cache(name, symbols, source_label)
        return symbols, UniverseMeta(ok=True, source=source_label, cached=False)
    except Exception as exc:
        logger.exception("Failed to fetch %s: %s", name, exc)
        stale = _load_disk_cache(name)
        if stale:
            return stale, UniverseMeta(
                ok=True,
                source=f"{source_label} (önbellek)",
                cached=True,
                message="Canlı liste alınamadı; kayıtlı önbellek kullanılıyor.",
            )
        raise RuntimeError(
            f"{source_label} listesi indirilemedi. İnternet / SSL ayarlarını kontrol edin. ({exc})"
        ) from exc


def _fetch_sp500_live() -> tuple[str, ...]:
    # 1) GitHub CSV (en güvenilir)
    try:
        text = _http_get(SP500_GITHUB_CSV)
        df = pd.read_csv(io.StringIO(text))
        col = "Symbol" if "Symbol" in df.columns else df.columns[0]
        syms = [_clean_symbol(s) for s in df[col].tolist()]
        out = tuple(sorted({s for s in syms if s}))
        if len(out) >= 400:
            return out
    except Exception as exc:
        logger.warning("SP500 GitHub fetch failed: %s", exc)

    # 2) Wikipedia HTML tablosu
    try:
        html = _http_get(SP500_WIKI_URL)
        tables = pd.read_html(io.StringIO(html))
        df = tables[0]
        syms = [_clean_symbol(s) for s in df["Symbol"].tolist()]
        out = tuple(sorted({s for s in syms if s}))
        if len(out) >= 400:
            return out
    except Exception as exc:
        logger.warning("SP500 Wikipedia fetch failed: %s", exc)

    raise ValueError("S&P 500 listesi alınamadı")


def _parse_nasdaq_pipe(text: str) -> tuple[str, ...]:
    lines = [ln for ln in text.splitlines() if ln.strip() and "File Creation Time" not in ln]
    reader = csv.DictReader(lines, delimiter="|")
    syms: list[str] = []
    for row in reader:
        if not nasdaq_listed_row_passes(row):
            continue
        sym = _clean_symbol(row.get("Symbol") or "")
        if sym:
            syms.append(sym)
    return tuple(sorted(set(syms)))


def _fetch_nasdaq_live() -> tuple[str, ...]:
    text = _http_get(NASDAQ_LISTED_URL)
    syms = _parse_nasdaq_pipe(text)
    if len(syms) < 400:
        raise ValueError(f"NASDAQ listesi eksik görünüyor ({len(syms)})")
    logger.info("NASDAQ common stocks: %d", len(syms))
    return syms


def _fetch_nyse_live() -> tuple[str, ...]:
    text = _http_get(OTHER_LISTED_URL)
    lines = [ln for ln in text.splitlines() if ln.strip() and "File Creation Time" not in ln]
    reader = csv.DictReader(lines, delimiter="|")
    syms: list[str] = []
    for row in reader:
        if not nyse_otherlisted_row_passes(row):
            continue
        sym = _clean_symbol(row.get("ACT Symbol") or row.get("Symbol") or "")
        if sym:
            syms.append(sym)
    out = tuple(sorted(set(syms)))
    if len(out) < 400:
        raise ValueError(f"NYSE listesi eksik görünüyor ({len(out)})")
    logger.info("NYSE common stocks: %d", len(out))
    return out


@lru_cache(maxsize=1)
def get_sp500_symbols() -> tuple[str, ...]:
    symbols, _ = _resolve_cached("sp500", _fetch_sp500_live, "S&P 500")
    return symbols


@lru_cache(maxsize=1)
def get_nasdaq_symbols() -> tuple[str, ...]:
    symbols, _ = _resolve_cached("nasdaq", _fetch_nasdaq_live, "NASDAQ")
    return symbols


@lru_cache(maxsize=1)
def get_nyse_symbols() -> tuple[str, ...]:
    symbols, _ = _resolve_cached("nyse", _fetch_nyse_live, "NYSE")
    return symbols


@lru_cache(maxsize=1)
def get_bist_symbols() -> tuple[str, ...]:
    symbols, _ = _resolve_cached("bist", fetch_bist_symbols_live, "BIST")
    return symbols


@lru_cache(maxsize=1)
def get_binance_symbols() -> tuple[str, ...]:
    symbols, _ = _resolve_cached(
        "binance", fetch_binance_usdt_symbols_live, "Binance Spot (USDT)"
    )
    return symbols


@lru_cache(maxsize=1)
def get_all_us_symbols() -> tuple[str, ...]:
    if _cache_fresh("all_us"):
        cached = _load_disk_cache("all_us")
        if cached:
            return cached
    combined = sorted(set(get_sp500_symbols()) | set(get_nasdaq_symbols()) | set(get_nyse_symbols()))
    out = tuple(combined)
    _save_disk_cache("all_us", out, "NASDAQ+NYSE+S&P500")
    return out


def get_universe_meta(universe: str) -> UniverseMeta:
    key = universe.lower()
    try:
        if key == "sp500":
            _, meta = _resolve_cached("sp500", _fetch_sp500_live, "S&P 500")
        elif key == "nasdaq":
            _, meta = _resolve_cached("nasdaq", _fetch_nasdaq_live, "NASDAQ")
        elif key == "nyse":
            _, meta = _resolve_cached("nyse", _fetch_nyse_live, "NYSE")
        elif key == "bist":
            _, meta = _resolve_cached("bist", fetch_bist_symbols_live, "BIST")
        elif key == "binance":
            _, meta = _resolve_cached(
                "binance", fetch_binance_usdt_symbols_live, "Binance Spot (USDT)"
            )
        elif key in ("all", "all_us", "us"):
            get_all_us_symbols()
            if _cache_fresh("all_us"):
                return UniverseMeta(ok=True, source="NASDAQ + NYSE + S&P 500", cached=True)
            return UniverseMeta(ok=True, source="NASDAQ + NYSE + S&P 500", cached=False)
        else:
            return UniverseMeta(ok=True, source=universe)
        return meta
    except Exception as exc:
        return UniverseMeta(ok=False, source=universe, message=str(exc))


def get_universe_symbols(universe: str) -> list[str]:
    key = universe.lower()
    if key == "sp500":
        return list(get_sp500_symbols())
    if key == "nasdaq":
        return list(get_nasdaq_symbols())
    if key == "nyse":
        return list(get_nyse_symbols())
    if key == "bist":
        return list(get_bist_symbols())
    if key == "binance":
        return list(get_binance_symbols())
    if key in ("all", "all_us", "us"):
        return list(get_all_us_symbols())
    return list(get_sp500_symbols())


def get_universe_count(universe: str) -> int:
    return len(get_universe_symbols(universe))


def refresh_universe_cache(universe: str | None = None) -> dict[str, int]:
    """Force refresh symbol lists (clears lru_cache and stale cache files)."""
    get_sp500_symbols.cache_clear()
    get_nasdaq_symbols.cache_clear()
    get_nyse_symbols.cache_clear()
    get_bist_symbols.cache_clear()
    get_binance_symbols.cache_clear()
    get_all_us_symbols.cache_clear()
    for legacy in CACHE_DIR.glob("*.json"):
        if f"_{SYMBOL_CACHE_VERSION}.json" not in legacy.name:
            try:
                legacy.unlink()
            except OSError:
                pass

    targets = (
        [universe]
        if universe and universe != "all_us"
        else ["sp500", "nasdaq", "nyse", "bist", "binance", "all_us"]
    )
    counts: dict[str, int] = {}
    for name in targets:
        if name == "all_us":
            counts[name] = len(get_all_us_symbols())
        else:
            counts[name] = get_universe_count(name)
    return counts


def parse_symbol_list(text: str, universe: str = "sp500") -> list[str]:
    raw = text.replace(",", "\n").replace(";", "\n").split("\n")
    if is_bist_universe(universe):
        return sorted({clean_bist_symbol(s) for s in raw if s.strip()})
    if is_binance_universe(universe):
        return sorted({clean_binance_symbol(s) for s in raw if s.strip()})
    return sorted({_clean_symbol(s) for s in raw if s.strip()})


def fetch_ohlcv(
    symbol: str,
    timeframe: str = DEFAULT_TIMEFRAME,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    universe: str = "sp500",
) -> pd.DataFrame | None:
    from app.services.ticker_format import to_yf_ticker

    if is_bist_universe(universe):
        from app.services.twelvedata_client import fetch_time_series

        return fetch_time_series(symbol, timeframe)

    if is_binance_universe(universe):
        from app.services.binance_data import fetch_ohlcv_batch_binance

        frames = fetch_ohlcv_batch_binance([symbol], timeframe)
        return frames.get(clean_binance_symbol(symbol))

    from app.services.batch_data import RESAMPLED_SOURCE_INTERVAL, RESAMPLED_SOURCE_PERIOD, RESAMPLED_TIMEFRAMES, _resample_ohlcv

    try:
        ticker = yf.Ticker(to_yf_ticker(symbol, universe))
        if timeframe in RESAMPLED_TIMEFRAMES:
            df = ticker.history(period=RESAMPLED_SOURCE_PERIOD, interval=RESAMPLED_SOURCE_INTERVAL, auto_adjust=True)
            df = df.rename(columns=str.title)
            df = _resample_ohlcv(df, RESAMPLED_TIMEFRAMES[timeframe])
            min_bars = INTRADAY_MIN_BARS
        elif timeframe in INTRADAY_TIMEFRAMES:
            df = ticker.history(period=INTRADAY_PERIOD, interval=timeframe, auto_adjust=True)
            min_bars = INTRADAY_MIN_BARS
        elif timeframe in ("1d", "1wk", "1mo"):
            period = f"{lookback_days}d" if timeframe == "1d" else "2y"
            df = ticker.history(period=period, interval=timeframe, auto_adjust=True)
            min_bars = 30
        else:
            df = ticker.history(period=INTRADAY_PERIOD, interval=timeframe, auto_adjust=True)
            min_bars = 30

        if df is None or df.empty or len(df) < min_bars:
            return None

        df = df.rename(columns=str.title)
        needed = {"Open", "High", "Low", "Close", "Volume"}
        if not needed.issubset(df.columns):
            return None

        return df[list(needed)].dropna()
    except Exception:
        return None
