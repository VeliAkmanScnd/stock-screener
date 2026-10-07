"""BIST (Borsa İstanbul) symbol list — multi-source (BigPara 403'e dayanıklı)."""

from __future__ import annotations

import csv
import io
import json
import logging
import re
from typing import Callable

import httpx

from app.config import BASE_DIR
from app.services.http_ssl import default_ssl_context
from app.services.ticker_format import clean_bist_symbol

logger = logging.getLogger(__name__)

SEED_PATH = BASE_DIR / "app" / "data" / "bist_symbols_seed.json"

# Community-maintained full BIST equity list (symbol column).
_GITHUB_CSV = (
    "https://raw.githubusercontent.com/ahmeterenodaci/"
    "Istanbul-Stock-Exchange--BIST--including-symbols-and-logos/main/bist.csv"
)
_JSDELIVR_CSV = (
    "https://cdn.jsdelivr.net/gh/ahmeterenodaci/"
    "Istanbul-Stock-Exchange--BIST--including-symbols-and-logos@main/bist.csv"
)
# Legacy — often 403; kept last.
_BIGPARA_URL = "https://bigpara.hurriyet.com.tr/api/v1/hisse/list"

_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/csv,application/json,text/plain,*/*",
}

MIN_BIST_SYMBOLS = 100


def _is_valid_bist_code(code: str) -> bool:
    if not code or len(code) > 6:
        return False
    return bool(re.fullmatch(r"[A-Z0-9]{2,6}", code))


def _normalize_codes(raw: list[str]) -> tuple[str, ...]:
    out = sorted(
        {
            clean_bist_symbol(s)
            for s in raw
            if _is_valid_bist_code(clean_bist_symbol(s))
        }
    )
    return tuple(out)


def _http_get_text(url: str, *, timeout: float = 90.0) -> str:
    with httpx.Client(
        verify=default_ssl_context(),
        timeout=timeout,
        follow_redirects=True,
        headers=_HTTP_HEADERS,
    ) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.text


def fetch_bist_symbols_csv(url: str) -> tuple[str, ...]:
    text = _http_get_text(url)
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("BIST CSV başlığı yok")
    # Prefer 'symbol'; fall back to common alternatives.
    fields = {str(f).strip().lower(): f for f in reader.fieldnames if f}
    symbol_key = (
        fields.get("symbol")
        or fields.get("kod")
        or fields.get("code")
        or fields.get("ticker")
        or reader.fieldnames[0]
    )
    syms: list[str] = []
    for row in reader:
        code = clean_bist_symbol(row.get(symbol_key) or "")
        if _is_valid_bist_code(code):
            syms.append(code)
    out = _normalize_codes(syms)
    if len(out) < MIN_BIST_SYMBOLS:
        raise ValueError(f"BIST CSV listesi eksik ({len(out)})")
    return out


def fetch_bist_symbols_bigpara() -> tuple[str, ...]:
    with httpx.Client(
        verify=default_ssl_context(),
        timeout=90.0,
        follow_redirects=True,
        headers={**_HTTP_HEADERS, "Accept": "application/json"},
    ) as client:
        response = client.get(_BIGPARA_URL)
        response.raise_for_status()
        payload = response.json()

    items = payload.get("data") or []
    syms: list[str] = []
    for item in items:
        if (item.get("tip") or "").strip() != "Hisse":
            continue
        code = clean_bist_symbol(item.get("kod") or "")
        if _is_valid_bist_code(code):
            syms.append(code)

    out = _normalize_codes(syms)
    if len(out) < MIN_BIST_SYMBOLS:
        raise ValueError(f"BIST BigPara listesi eksik ({len(out)})")
    return out


def fetch_bist_symbols_twelvedata() -> tuple[str, ...]:
    from app.config import TWELVE_DATA_API_KEY
    from app.services.twelvedata_client import fetch_bist_symbol_list

    if not (TWELVE_DATA_API_KEY or "").strip():
        raise ValueError("Twelve Data API anahtarı yok")
    return fetch_bist_symbol_list()


def load_bist_symbols_seed() -> tuple[str, ...]:
    if not SEED_PATH.is_file():
        raise FileNotFoundError(f"BIST seed yok: {SEED_PATH}")
    payload = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    out = _normalize_codes([str(s) for s in (payload.get("symbols") or [])])
    if len(out) < MIN_BIST_SYMBOLS:
        raise ValueError(f"BIST seed eksik ({len(out)})")
    return out


def fetch_bist_symbols_live() -> tuple[str, ...]:
    """Full BIST equity list with fallbacks (GitHub → CDN → TD → BigPara → seed)."""
    from app.services.bist_blocklist import filter_bist_blocklist

    sources: list[tuple[str, Callable[[], tuple[str, ...]]]] = [
        ("github_csv", lambda: fetch_bist_symbols_csv(_GITHUB_CSV)),
        ("jsdelivr_csv", lambda: fetch_bist_symbols_csv(_JSDELIVR_CSV)),
        ("twelvedata", fetch_bist_symbols_twelvedata),
        ("bigpara", fetch_bist_symbols_bigpara),
        ("seed", load_bist_symbols_seed),
    ]
    errors: list[str] = []
    for name, fetcher in sources:
        try:
            syms = filter_bist_blocklist(fetcher())
            if len(syms) < MIN_BIST_SYMBOLS:
                raise ValueError(f"filtre sonrası eksik ({len(syms)})")
            logger.info("BIST symbols from %s: %d", name, len(syms))
            return syms
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            logger.warning("BIST list source %s failed: %s", name, exc)

    detail = " | ".join(errors[-3:]) if errors else "bilinmeyen hata"
    raise RuntimeError(f"BIST listesi hiçbir kaynaktan alınamadı ({detail})")
