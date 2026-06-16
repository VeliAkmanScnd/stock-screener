"""TradingView watchlist text export."""

from __future__ import annotations

from app.services.ticker_format import is_bist_universe, is_binance_universe, to_binance_pair


def to_tradingview_symbol(symbol: str, universe: str) -> str:
    sym = symbol.strip().upper()
    if is_bist_universe(universe):
        if sym.startswith("BIST:"):
            return sym
        return f"BIST:{sym}"
    if is_binance_universe(universe):
        if sym.startswith("BINANCE:"):
            return sym
        pair = to_binance_pair(sym)
        return f"BINANCE:{pair}" if pair else sym
    return sym


def build_tradingview_list(symbols: list[str], universe: str) -> str:
    lines = [to_tradingview_symbol(s, universe) for s in symbols if s and str(s).strip()]
    return "\n".join(sorted(set(lines)))
