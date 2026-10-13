"""Map display symbols to Yahoo Finance tickers by market."""

from __future__ import annotations

import re

BIST_YF_SUFFIX = ".IS"
BIST_UNIVERSES = frozenset({"bist", "borsa_istanbul", "istanbul", "borsa"})
VIOP_UNIVERSES = frozenset({"viop", "vadeli", "viop_futures"})
BINANCE_UNIVERSES = frozenset({"binance", "binance_spot", "crypto"})
FX_UNIVERSES = frozenset({"fx", "forex", "parite"})
BINANCE_QUOTE = "USDT"
_FX_ALIASES = {
    "XAU": "XAUUSD",
    "XAG": "XAGUSD",
    "GOLD": "XAUUSD",
    "SILVER": "XAGUSD",
}


def is_bist_universe(universe: str) -> bool:
    return (universe or "").lower() in BIST_UNIVERSES


def is_binance_universe(universe: str) -> bool:
    return (universe or "").lower() in BINANCE_UNIVERSES


def is_viop_universe(universe: str) -> bool:
    return (universe or "").lower() in VIOP_UNIVERSES


def is_fx_universe(universe: str) -> bool:
    return (universe or "").lower() in FX_UNIVERSES


def clean_fx_symbol(sym: str) -> str:
    s = str(sym).strip().upper().replace("/", "").replace("-", "").replace(" ", "")
    if ":" in s:
        s = s.split(":")[-1]
    if s.endswith("=X"):
        s = s[:-2]
    return _FX_ALIASES.get(s, s)


def clean_viop_symbol(sym: str) -> str:
    s = str(sym).strip().upper().replace(" ", "")
    if s.startswith("BIST:"):
        s = s.split(":", 1)[1]
    if s.endswith(BIST_YF_SUFFIX):
        s = s[: -len(BIST_YF_SUFFIX)]
    return s


def viop_underlying(symbol: str) -> str:
    """F_THYAO1026 / F_XU0301026 -> THYAO / XU030."""
    s = clean_viop_symbol(symbol)
    m = re.fullmatch(r"F_([A-Z0-9]{2,8})\d{4}", s)
    if m:
        return m.group(1)
    if s.startswith("F_") and len(s) > 2:
        return s[2:]
    return s


def to_viop_continuous_symbol(symbol: str) -> str:
    """F_AEFES1026 / AEFES -> AEFES1! (TradingView continuous)."""
    s = clean_viop_symbol(symbol)
    if s.endswith("1!"):
        return s
    und = viop_underlying(s)
    if und.endswith("1!"):
        return und
    return f"{und}1!" if und else s


def clean_bist_symbol(sym: str) -> str:
    s = str(sym).strip().upper()
    if s.endswith(BIST_YF_SUFFIX):
        s = s[: -len(BIST_YF_SUFFIX)]
    return s


def clean_us_symbol(sym: str) -> str:
    return str(sym).strip().upper().replace(".", "-")


def clean_binance_symbol(sym: str) -> str:
    s = str(sym).strip().upper().replace("/", "").replace("-", "")
    if s.endswith(BINANCE_QUOTE):
        s = s[: -len(BINANCE_QUOTE)]
    if s.startswith("BINANCE:"):
        s = s.split(":", 1)[1]
        if s.endswith(BINANCE_QUOTE):
            s = s[: -len(BINANCE_QUOTE)]
    return s


def to_binance_pair(symbol: str) -> str:
    base = clean_binance_symbol(symbol)
    if not base:
        return ""
    return f"{base}{BINANCE_QUOTE}"


def to_yf_ticker(symbol: str, universe: str) -> str:
    if is_bist_universe(universe) or is_viop_universe(universe):
        base = viop_underlying(symbol) if is_viop_universe(universe) else clean_bist_symbol(symbol)
        if not base:
            return ""
        return f"{base}{BIST_YF_SUFFIX}"
    if is_binance_universe(universe):
        base = clean_binance_symbol(symbol)
        if not base:
            return ""
        return f"{base}-USD"
    if is_fx_universe(universe):
        from app.services.fx_data import yf_symbol

        return yf_symbol(symbol)
    return clean_us_symbol(symbol)


def from_yf_ticker(yf_symbol: str, universe: str) -> str:
    if is_bist_universe(universe) or is_viop_universe(universe):
        return clean_bist_symbol(yf_symbol)
    if is_binance_universe(universe):
        return clean_binance_symbol(yf_symbol.replace("-USD", ""))
    if is_fx_universe(universe):
        from app.services.fx_data import display_symbol

        return display_symbol(yf_symbol) or clean_fx_symbol(yf_symbol)
    return clean_us_symbol(yf_symbol)
