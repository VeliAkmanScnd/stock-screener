"""BIST (Borsa İstanbul) symbol list."""

from __future__ import annotations

import logging
import re

import httpx

from app.services.http_ssl import default_ssl_context
from app.services.ticker_format import clean_bist_symbol

logger = logging.getLogger(__name__)

BIST_LIST_URL = "https://bigpara.hurriyet.com.tr/api/v1/hisse/list"

_HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; StockScreener/1.0)",
    "Accept": "application/json",
}


def _is_valid_bist_code(code: str) -> bool:
    if not code or len(code) > 6:
        return False
    return bool(re.fullmatch(r"[A-Z0-9]{2,6}", code))


def fetch_bist_symbols_bigpara() -> tuple[str, ...]:
    with httpx.Client(
        verify=default_ssl_context(),
        timeout=90.0,
        follow_redirects=True,
        headers=_HTTP_HEADERS,
    ) as client:
        response = client.get(BIST_LIST_URL)
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

    out = tuple(sorted(set(syms)))
    if len(out) < 100:
        raise ValueError(f"BIST listesi eksik görünüyor ({len(out)})")
    return out


def fetch_bist_symbols_live() -> tuple[str, ...]:
    """BigPara public list (no API key; matches yfinance .IS tickers)."""
    from app.services.bist_blocklist import filter_bist_blocklist

    syms = fetch_bist_symbols_bigpara()
    syms = filter_bist_blocklist(syms)
    logger.info("BIST symbols from BigPara: %d", len(syms))
    return syms
