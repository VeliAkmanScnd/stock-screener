"""Binance Spot USDT trading pairs (public API)."""

from __future__ import annotations

import logging
import re

import httpx

from app.services.http_ssl import default_ssl_context

from app.services.ticker_format import clean_binance_symbol

logger = logging.getLogger(__name__)

BINANCE_EXCHANGE_INFO = "https://api.binance.com/api/v3/exchangeInfo"
QUOTE_ASSET = "USDT"

# Stable / fiat bases — not useful as scan targets
EXCLUDED_BASES = frozenset(
    {
        "USDT",
        "USDC",
        "BUSD",
        "TUSD",
        "FDUSD",
        "DAI",
        "USDP",
        "EUR",
        "GBP",
        "AEUR",
        "USD1",
    }
)

_LEVERAGED_RE = re.compile(r"^(.*)(UP|DOWN|BULL|BEAR|[23][LS])$", re.I)


def _is_leveraged_token(base: str) -> bool:
    if len(base) > 12:
        return True
    m = _LEVERAGED_RE.match(base)
    if not m:
        return False
    stem = m.group(1)
    return len(stem) >= 2


def fetch_binance_usdt_symbols_live() -> tuple[str, ...]:
    """Active Binance Spot symbols quoted in USDT (base asset as display ticker)."""
    with httpx.Client(
        verify=default_ssl_context(),
        timeout=90.0,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (compatible; StockScreener/1.0)"},
    ) as client:
        response = client.get(BINANCE_EXCHANGE_INFO)
        response.raise_for_status()
        payload = response.json()

    syms: list[str] = []
    for item in payload.get("symbols") or []:
        if item.get("status") != "TRADING":
            continue
        if item.get("quoteAsset") != QUOTE_ASSET:
            continue
        if item.get("isSpotTradingAllowed") is False:
            continue
        base = clean_binance_symbol(item.get("baseAsset") or "")
        if not base or base in EXCLUDED_BASES:
            continue
        if _is_leveraged_token(base):
            continue
        if not re.fullmatch(r"[A-Z0-9]{2,15}", base):
            continue
        syms.append(base)

    out = tuple(sorted(set(syms)))
    if len(out) < 50:
        raise ValueError(f"Binance listesi eksik görünüyor ({len(out)})")
    logger.info("Binance USDT spot pairs: %d", len(out))
    return out
