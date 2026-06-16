"""Map display symbols to Yahoo Finance tickers by market."""

from __future__ import annotations

BIST_YF_SUFFIX = ".IS"
BIST_UNIVERSES = frozenset({"bist", "borsa_istanbul", "istanbul", "borsa"})
BINANCE_UNIVERSES = frozenset({"binance", "binance_spot", "crypto"})
BINANCE_QUOTE = "USDT"


def is_bist_universe(universe: str) -> bool:
    return (universe or "").lower() in BIST_UNIVERSES


def is_binance_universe(universe: str) -> bool:
    return (universe or "").lower() in BINANCE_UNIVERSES


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
    if is_bist_universe(universe):
        base = clean_bist_symbol(symbol)
        if not base:
            return ""
        return f"{base}{BIST_YF_SUFFIX}"
    if is_binance_universe(universe):
        base = clean_binance_symbol(symbol)
        if not base:
            return ""
        return f"{base}-USD"
    return clean_us_symbol(symbol)


def from_yf_ticker(yf_symbol: str, universe: str) -> str:
    if is_bist_universe(universe):
        return clean_bist_symbol(yf_symbol)
    if is_binance_universe(universe):
        return clean_binance_symbol(yf_symbol.replace("-USD", ""))
    return clean_us_symbol(yf_symbol)
