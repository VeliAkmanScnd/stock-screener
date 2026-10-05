"""Drop repeat scan hits that still fire at the same price."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.database import ScanSignalLast
from app.services.tv_export import build_tradingview_list


def _direction(signals: Any) -> str:
    if not isinstance(signals, dict):
        return "AL"
    buy = bool(
        signals.get("bias_ts_buy") or signals.get("guven_buy") or signals.get("buy")
    )
    sell = bool(
        signals.get("bias_ts_sell") or signals.get("guven_sell") or signals.get("sell")
    )
    if buy and sell:
        side = str(
            signals.get("bias_ts_side")
            or signals.get("guven_side")
            or signals.get("side")
            or "buy"
        ).strip().lower()
        return "SAT" if side == "sell" else "AL"
    if sell and not buy:
        return "SAT"
    return "AL"


def _price_key(value: Any) -> float | None:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    if price != price:
        return None
    return round(price, 2)


def scan_fingerprint(
    *,
    user_id: int,
    scheduled_scan_id: int | None = None,
    universe: str = "",
    timeframe: str = "",
    custom_source_universe: str | None = None,
    pine_script_id: int | None = None,
) -> str:
    if scheduled_scan_id:
        return f"s:{int(scheduled_scan_id)}"
    src = (custom_source_universe or "").strip().lower()
    return (
        f"m:{int(user_id)}:{(universe or '').strip().lower()}:"
        f"{src}:{(timeframe or '').strip().lower()}:{int(pine_script_id or 0)}"
    )


def apply_repeat_price_filter(
    db: Session,
    payload: dict[str, Any],
    *,
    user_id: int | None,
    fingerprint: str | None,
) -> dict[str, Any]:
    """Keep the first new (symbol, direction, price); hide same-price repeats.

    Updates stored last prices for kept rows so the next run can skip them.
    """
    results = list(payload.get("results") or [])
    skipped = 0
    kept: list[dict[str, Any]] = []
    seen_batch: set[tuple[str, str, float]] = set()

    last_map: dict[tuple[str, str], float] = {}
    if user_id and fingerprint:
        rows = (
            db.query(ScanSignalLast)
            .filter(
                ScanSignalLast.user_id == user_id,
                ScanSignalLast.fingerprint == fingerprint,
            )
            .all()
        )
        last_map = {
            (str(row.symbol).upper(), str(row.direction or "AL")): round(float(row.price), 2)
            for row in rows
        }

    now = datetime.now(timezone.utc)
    to_upsert: dict[tuple[str, str], float] = {}

    for item in results:
        symbol = str(item.get("symbol") or "").strip().upper()
        price = _price_key(item.get("price"))
        if not symbol or price is None:
            skipped += 1
            continue
        direction = _direction(item.get("signals"))
        batch_key = (symbol, direction, price)
        if batch_key in seen_batch:
            skipped += 1
            continue
        seen_batch.add(batch_key)
        last_price = last_map.get((symbol, direction))
        if last_price is not None and last_price == price:
            skipped += 1
            continue
        kept.append(item)
        to_upsert[(symbol, direction)] = price

    if user_id and fingerprint and to_upsert:
        existing = {
            (str(row.symbol).upper(), str(row.direction or "AL")): row
            for row in (
                db.query(ScanSignalLast)
                .filter(
                    ScanSignalLast.user_id == user_id,
                    ScanSignalLast.fingerprint == fingerprint,
                )
                .all()
            )
        }
        for (symbol, direction), price in to_upsert.items():
            row = existing.get((symbol, direction))
            if row:
                row.price = price
                row.updated_at = now
            else:
                db.add(
                    ScanSignalLast(
                        user_id=user_id,
                        fingerprint=fingerprint[:255],
                        symbol=symbol[:32],
                        direction=direction[:8],
                        price=price,
                        updated_at=now,
                    )
                )
        db.commit()

    universe = str(payload.get("universe") or "sp500")
    tv_text = (
        build_tradingview_list([str(row.get("symbol") or "") for row in kept], universe)
        if kept
        else ""
    )
    payload["results"] = kept
    payload["count"] = len(kept)
    payload["skipped_repeat_price"] = skipped
    payload["tradingview_text"] = tv_text
    payload["tradingview_symbols"] = tv_text.split("\n") if tv_text else []
    stats = payload.get("stats")
    if isinstance(stats, dict):
        stats["skipped_repeat_price"] = skipped
    return payload
