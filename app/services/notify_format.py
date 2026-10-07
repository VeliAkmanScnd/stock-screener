"""Shared formatting for scan email / notification bodies."""

from __future__ import annotations

from typing import Any


def format_match_lines_for_email(
    results: list[dict[str, Any]] | None,
    *,
    timeframe: str | None = None,
) -> str:
    """One line per match: SYMBOL  price  yön  bar."""
    from app.services.bar_close import format_bar_label
    from app.services.track_service import signal_direction

    lines: list[str] = []
    for row in results or []:
        symbol = str(row.get("symbol") or "").strip()
        if not symbol:
            continue
        try:
            price = float(row.get("price"))
        except (TypeError, ValueError):
            price = None
        signals = row.get("signals") if isinstance(row.get("signals"), dict) else {}
        direction = signal_direction(signals)
        bar = str(signals.get("bar_label") or "").strip()
        if not bar and signals.get("bar_time"):
            bar = format_bar_label(signals.get("bar_time"), timeframe) or ""
        price_s = f"{price:.4g}" if price is not None and price == price else "—"
        parts = [symbol, price_s, direction]
        if bar:
            parts.append(bar)
        lines.append("  ".join(parts))
    return "\n".join(lines)
