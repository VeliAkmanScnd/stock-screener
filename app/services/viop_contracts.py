"""Daily VIOP calculator contract refresh: live prices + margin rates → leverage."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import httpx

from app.config import BASE_DIR, STORAGE_DIR
from app.services.ticker_format import clean_viop_symbol, viop_underlying

logger = logging.getLogger(__name__)

SEED_PATH = BASE_DIR / "app" / "data" / "viop_contracts_seed.json"
SNAPSHOT_DIR = STORAGE_DIR / "viop_contracts"
SNAPSHOT_PATH = SNAPSHOT_DIR / "latest.json"
OSMANLI_URL = (
    "https://www.osmanlimenkul.com.tr/hisse-ve-viop/"
    "hisse-ve-viop-urunlerimiz/hisse-turev/viop-teminat-ve-limit-bilgileri"
)

# Calculator ticker → VIOP board underlying (and reverse aliases).
CALC_TO_BOARD = {
    "BIST30": "XU030",
    "XAUTRY": "XAUTRYM",
}
BOARD_TO_CALC = {v: k for k, v in CALC_TO_BOARD.items()}
# Osmanlı / board symbols that map to calculator tickers.
RATE_ALIASES = {
    "XU030": "BIST30",
    "XAUTRYM": "XAUTRY",
}


class _RateTableParser(HTMLParser):
    """Extract symbol → margin rate % pairs from Osmanlı HTML tables."""

    def __init__(self) -> None:
        super().__init__()
        self.in_td = False
        self.cells: list[str] = []
        self.row: list[str] = []
        self.rates: dict[str, float] = {}

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "td":
            self.in_td = True
            self.cells = []
        elif tag == "tr":
            self.row = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self.in_td:
            self.in_td = False
            text = " ".join(self.cells).strip()
            self.row.append(text)
        elif tag == "tr" and len(self.row) >= 2:
            sym = re.sub(r"\s+", "", self.row[0]).upper()
            rate_txt = self.row[1]
            # Only PSR rows contain "%"; skip azami kontrat limit tables.
            if re.fullmatch(r"[A-Z0-9]{2,10}", sym) and "%" in rate_txt:
                m = re.search(r"%\s*([0-9]+(?:[.,][0-9]+)?)", rate_txt)
                if m:
                    rate = float(m.group(1).replace(",", "."))
                    if 1.0 <= rate <= 80.0:
                        self.rates[sym] = rate
            self.row = []

    def handle_data(self, data: str) -> None:
        if self.in_td:
            self.cells.append(data)


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("VIOP contracts JSON read failed %s: %s", path, exc)
        return None


def _seed_contracts() -> list[dict[str, Any]]:
    data = _load_json(SEED_PATH) or {}
    rows = data.get("contracts") or []
    return [dict(r) for r in rows if r.get("ticker")]


def _normalize_contract(row: dict[str, Any]) -> dict[str, Any]:
    ticker = str(row.get("ticker") or "").strip().upper()
    price = float(row.get("price") or 0)
    margin = float(row.get("margin") or 0)
    multiplier = float(row.get("multiplier") or 0)
    rate = row.get("margin_rate_pct")
    if rate is None and price > 0 and multiplier > 0 and margin > 0:
        rate = margin / (price * multiplier) * 100
    rate_f = float(rate or 0)
    if price > 0 and multiplier > 0 and rate_f > 0:
        margin = round(price * multiplier * rate_f / 100, 2)
        leverage = round((price * multiplier) / margin, 2) if margin else 0.0
    else:
        leverage = float(row.get("leverage") or 0)
    return {
        "ticker": ticker,
        "name": str(row.get("name") or ticker),
        "margin": margin,
        "price": price,
        "leverage": leverage,
        "multiplier": multiplier,
        "currency": str(row.get("currency") or "TL"),
        "group": str(row.get("group") or "pay"),
        "margin_rate_pct": round(rate_f, 4),
    }


def load_snapshot() -> dict[str, Any]:
    """Latest snapshot, or seed fallback."""
    data = _load_json(SNAPSHOT_PATH)
    if data and data.get("contracts"):
        return data
    contracts = [_normalize_contract(r) for r in _seed_contracts()]
    return {
        "updated_at": None,
        "source": "seed",
        "price_updates": 0,
        "rate_updates": 0,
        "contracts": contracts,
    }


def fetch_board_prices() -> dict[str, float]:
    """Front-month last price per board underlying (max volume)."""
    import borsapy as bp

    board = bp.VIOP()
    frames = [
        board.index_futures,
        board.stock_futures,
        board.currency_futures,
        board.commodity_futures,
    ]
    best: dict[str, tuple[float, float]] = {}
    for frame in frames:
        if frame is None or frame.empty:
            continue
        for _, row in frame.iterrows():
            code = clean_viop_symbol(row.get("code") or "")
            if not code.startswith("F_"):
                continue
            und = viop_underlying(code)
            if not und:
                continue
            # Strip trailing month letter quirks like XAUTRYM already handled by und.
            try:
                price = float(row.get("price") or 0)
            except (TypeError, ValueError):
                continue
            if price <= 0:
                continue
            vol = float(row.get("volume_qty") or 0) or 0.0
            prev = best.get(und)
            if prev is None or vol > prev[1]:
                best[und] = (price, vol)

    out: dict[str, float] = {}
    for und, (price, _) in best.items():
        calc = BOARD_TO_CALC.get(und, und)
        out[calc] = price
        out[und] = price
    return out


def fetch_osmanli_margin_rates(timeout: float = 25.0) -> dict[str, float]:
    """Broker PSR-style margin rates (%). Empty dict on failure."""
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(
                OSMANLI_URL,
                headers={"User-Agent": "TradeLABtr/1.0 (+viop-contracts-refresh)"},
            )
            resp.raise_for_status()
            html = resp.text
    except Exception as exc:
        logger.warning("Osmanlı teminat oranları alınamadı: %s", exc)
        return {}

    parser = _RateTableParser()
    try:
        parser.feed(html)
    except Exception as exc:
        logger.warning("Osmanlı HTML parse failed: %s", exc)
        return {}

    mapped: dict[str, float] = {}
    for sym, rate in parser.rates.items():
        if rate <= 0 or rate > 100:
            continue
        calc = RATE_ALIASES.get(sym, sym)
        mapped[calc] = rate
    logger.info("Osmanlı margin rates: %d symbols", len(mapped))
    return mapped


def refresh_viop_contracts(*, force: bool = True) -> dict[str, Any]:
    """
    Refresh prices from borsapy VIOP board and margin rates from Osmanlı.
    Recomputes margin TL and leverage. Keeps previous snapshot on total failure.
    """
    del force  # always rebuild from seed+previous+live
    base_rows = {c["ticker"]: c for c in _seed_contracts()}
    prev = load_snapshot()
    for row in prev.get("contracts") or []:
        t = str(row.get("ticker") or "").upper()
        if t and t in base_rows:
            # Prefer last known live price/rate as starting point.
            base_rows[t] = {**base_rows[t], **row, "ticker": t}

    prices: dict[str, float] = {}
    rates: dict[str, float] = {}
    price_err = None
    rate_err = None
    try:
        prices = fetch_board_prices()
    except Exception as exc:
        price_err = str(exc)
        logger.exception("VIOP board prices failed")
    try:
        rates = fetch_osmanli_margin_rates()
    except Exception as exc:
        rate_err = str(exc)
        logger.exception("VIOP margin rates failed")

    price_updates = 0
    rate_updates = 0
    contracts: list[dict[str, Any]] = []
    for ticker in sorted(base_rows.keys()):
        row = dict(base_rows[ticker])
        if ticker in prices:
            row["price"] = float(prices[ticker])
            price_updates += 1
        if ticker in rates:
            row["margin_rate_pct"] = float(rates[ticker])
            rate_updates += 1
        contracts.append(_normalize_contract(row))

    if not contracts:
        raise ValueError("VIOP kontrat listesi boş")

    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "live",
        "price_updates": price_updates,
        "rate_updates": rate_updates,
        "price_error": price_err,
        "rate_error": rate_err,
        "contracts": contracts,
    }
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SNAPSHOT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(SNAPSHOT_PATH)
    logger.info(
        "VIOP contracts refreshed: %d contracts, prices=%d rates=%d",
        len(contracts),
        price_updates,
        rate_updates,
    )
    return {
        "ok": True,
        "updated_at": payload["updated_at"],
        "contracts": len(contracts),
        "price_updates": price_updates,
        "rate_updates": rate_updates,
        "price_error": price_err,
        "rate_error": rate_err,
        "path": str(SNAPSHOT_PATH),
    }


def get_viop_contracts_payload() -> dict[str, Any]:
    """API payload; refresh once if no snapshot yet."""
    data = load_snapshot()
    if data.get("source") == "seed" or not data.get("updated_at"):
        try:
            refresh_viop_contracts()
            data = load_snapshot()
        except Exception:
            logger.exception("VIOP contracts warm refresh failed; serving seed")
    # Strip internal-only fields for clients if needed — keep rates for transparency.
    return {
        "updated_at": data.get("updated_at"),
        "source": data.get("source"),
        "price_updates": data.get("price_updates"),
        "rate_updates": data.get("rate_updates"),
        "contracts": data.get("contracts") or [],
    }
