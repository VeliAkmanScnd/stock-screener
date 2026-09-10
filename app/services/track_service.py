"""Performance tracking: ingest scan matches, update prices, TP/SL."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.config import DEFAULT_SCHEDULE_TIMEZONE, TRACK_DEFAULT_STOP_PCT, TRACK_DEFAULT_TARGET_PCT
from app.database import TrackBenchmarkLog, TrackPosition, TrackPriceLog, TrackUserSettings
from app.services.track_benchmarks import benchmark_meta, fetch_benchmark_price, fetch_benchmark_prices
from app.services.track_prices import fetch_latest_prices
from app.utils.datetime_fmt import utc_iso

logger = logging.getLogger(__name__)

INTRADAY_TIMEFRAMES = frozenset({"5m", "15m", "30m", "1h", "4h", "8h", "12h"})
ACTIVE_STATUS = "active"
CLOSED_STATUSES = frozenset({"hit_target", "hit_stop", "expired", "manual_close"})

UNIVERSE_LABELS: dict[str, str] = {
    "bist": "BIST",
    "sp500": "S&P 500",
    "nasdaq": "NASDAQ",
    "nyse": "NYSE",
    "all_us": "US (tümü)",
    "binance": "Binance",
    "custom": "Özel",
}


def log_benchmark(db: Session, universe: str, price: float, *, at: datetime | None = None) -> None:
    db.add(
        TrackBenchmarkLog(
            universe=(universe or "").lower(),
            price=float(price),
            recorded_at=at or datetime.now(timezone.utc),
        )
    )


def _apply_benchmark_entry(row: TrackPosition, universe: str, price: float | None) -> None:
    meta = benchmark_meta(universe)
    if not meta or price is None:
        return
    row.benchmark_symbol = meta["label"]
    row.benchmark_entry_price = float(price)


def _ensure_position_benchmark(
    db: Session,
    row: TrackPosition,
    universe: str,
    current_px: float | None,
) -> None:
    if current_px is None:
        return
    if row.benchmark_entry_price is None:
        first_log = (
            db.query(TrackBenchmarkLog)
            .filter(
                TrackBenchmarkLog.universe == universe,
                TrackBenchmarkLog.recorded_at >= row.entry_at,
            )
            .order_by(TrackBenchmarkLog.recorded_at.asc())
            .first()
        )
        ref = first_log.price if first_log else current_px
        _apply_benchmark_entry(row, universe, ref)
    row.benchmark_current_price = float(current_px)


def _benchmark_points_for_position(
    db: Session,
    row: TrackPosition,
) -> list[dict[str, Any]]:
    entry_px = row.benchmark_entry_price
    if entry_px is None or not entry_px:
        first_log = (
            db.query(TrackBenchmarkLog)
            .filter(
                TrackBenchmarkLog.universe == row.universe,
                TrackBenchmarkLog.recorded_at >= row.entry_at,
            )
            .order_by(TrackBenchmarkLog.recorded_at.asc())
            .first()
        )
        if first_log:
            entry_px = first_log.price
    if entry_px is None or not entry_px:
        return []

    logs = (
        db.query(TrackBenchmarkLog)
        .filter(
            TrackBenchmarkLog.universe == row.universe,
            TrackBenchmarkLog.recorded_at >= row.entry_at,
        )
        .order_by(TrackBenchmarkLog.recorded_at.asc())
        .all()
    )

    points: list[dict[str, Any]] = [
        {
            "recorded_at": utc_iso(row.entry_at),
            "price": entry_px,
            "change_pct": 0.0,
        }
    ]
    for log in logs:
        points.append(
            {
                "recorded_at": utc_iso(log.recorded_at),
                "price": log.price,
                "change_pct": pct_change(entry_px, log.price),
            }
        )
    return points


def _align_benchmark_to_stock(
    stock_points: list[dict[str, Any]],
    benchmark_points: list[dict[str, Any]],
) -> list[float | None]:
    if not benchmark_points or not stock_points:
        return [None] * len(stock_points)

    aligned: list[float | None] = []
    b_idx = 0
    for sp in stock_points:
        sp_ts = sp.get("recorded_at") or ""
        while b_idx + 1 < len(benchmark_points) and (benchmark_points[b_idx + 1]["recorded_at"] or "") <= sp_ts:
            b_idx += 1
        chg = benchmark_points[b_idx].get("change_pct")
        aligned.append(chg if chg is not None else 0.0)
    return aligned


def log_price(
    db: Session,
    position_id: int,
    price: float,
    *,
    at: datetime | None = None,
) -> None:
    db.add(
        TrackPriceLog(
            position_id=position_id,
            price=float(price),
            recorded_at=at or datetime.now(timezone.utc),
        )
    )


def get_or_create_settings(db: Session, user_id: int) -> TrackUserSettings:
    row = db.query(TrackUserSettings).filter(TrackUserSettings.user_id == user_id).first()
    if row:
        return row
    row = TrackUserSettings(
        user_id=user_id,
        target_pct=TRACK_DEFAULT_TARGET_PCT,
        stop_pct=TRACK_DEFAULT_STOP_PCT,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def calc_levels(entry: float, target_pct: float, stop_pct: float) -> tuple[float, float]:
    return (
        round(entry * (1 + target_pct / 100), 6),
        round(entry * (1 - stop_pct / 100), 6),
    )


def pct_change(entry: float, current: float | None) -> float | None:
    if current is None or not entry:
        return None
    return round((current - entry) / entry * 100, 2)


def position_to_dict(row: TrackPosition) -> dict[str, Any]:
    chg = pct_change(row.entry_price, row.current_price)
    bm_chg = pct_change(row.benchmark_entry_price, row.benchmark_current_price)
    return {
        "id": row.id,
        "symbol": row.symbol,
        "universe": row.universe,
        "entry_price": row.entry_price,
        "entry_at": utc_iso(row.entry_at),
        "target_price": row.target_price,
        "stop_price": row.stop_price,
        "target_pct": row.target_pct,
        "stop_pct": row.stop_pct,
        "current_price": row.current_price,
        "change_pct": chg,
        "last_checked_at": utc_iso(row.last_checked_at),
        "status": row.status,
        "source_type": row.source_type,
        "scheduled_scan_id": row.scheduled_scan_id,
        "scan_run_id": row.scan_run_id,
        "source_label": row.source_label,
        "schedule_type": row.schedule_type,
        "timeframe": row.timeframe,
        "exit_price": row.exit_price,
        "exit_at": utc_iso(row.exit_at),
        "exit_reason": row.exit_reason,
        "benchmark_symbol": row.benchmark_symbol,
        "benchmark_entry_price": row.benchmark_entry_price,
        "benchmark_current_price": row.benchmark_current_price,
        "benchmark_change_pct": bm_chg,
        "created_at": utc_iso(row.created_at),
    }


def ingest_scan_results(
    db: Session,
    *,
    user_id: int,
    payload: dict[str, Any],
    source_type: str,
    source_label: str,
    scheduled_scan_id: int | None = None,
    scan_run_id: int | None = None,
    schedule_type: str | None = None,
) -> int:
    settings = get_or_create_settings(db, user_id)
    if not settings.auto_track_enabled and source_type == "scheduled":
        return 0

    results = payload.get("results") or []
    if not results:
        return 0

    universe = payload.get("universe") or "sp500"
    timeframe = payload.get("timeframe") or "1d"
    now = datetime.now(timezone.utc)
    added = 0
    benchmark_px = fetch_benchmark_price(universe)
    if benchmark_px is not None:
        log_benchmark(db, universe, benchmark_px, at=now)

    for item in results:
        symbol = str(item.get("symbol") or "").strip().upper()
        price = item.get("price")
        if not symbol or price is None:
            continue
        entry = float(price)
        if scan_run_id is not None:
            exists = (
                db.query(TrackPosition)
                .filter(
                    TrackPosition.scan_run_id == scan_run_id,
                    TrackPosition.symbol == symbol,
                )
                .first()
            )
            if exists:
                continue

        target_pct = float(settings.target_pct)
        stop_pct = float(settings.stop_pct)
        target_price, stop_price = calc_levels(entry, target_pct, stop_pct)
        row = TrackPosition(
            user_id=user_id,
            symbol=symbol,
            universe=universe,
            entry_price=entry,
            entry_at=now,
            target_price=target_price,
            stop_price=stop_price,
            target_pct=target_pct,
            stop_pct=stop_pct,
            current_price=entry,
            last_checked_at=now,
            status=ACTIVE_STATUS,
            source_type=source_type,
            scheduled_scan_id=scheduled_scan_id,
            scan_run_id=scan_run_id,
            source_label=source_label,
            schedule_type=schedule_type,
            timeframe=timeframe,
        )
        _apply_benchmark_entry(row, universe, benchmark_px)
        if benchmark_px is not None:
            row.benchmark_current_price = float(benchmark_px)
        db.add(row)
        db.flush()
        log_price(db, row.id, entry, at=now)
        added += 1

    if added:
        db.commit()
        logger.info("Track: added %s positions for user %s (%s)", added, user_id, source_label)
    return added


def _close_position(
    row: TrackPosition,
    *,
    reason: str,
    exit_price: float | None,
    now: datetime,
) -> None:
    row.status = reason
    row.exit_reason = reason
    row.exit_price = exit_price if exit_price is not None else row.current_price
    row.exit_at = now
    if exit_price is not None:
        row.current_price = exit_price
    row.last_checked_at = now


def _reopen_position(row: TrackPosition, now: datetime) -> None:
    row.status = ACTIVE_STATUS
    row.exit_reason = None
    row.exit_price = None
    row.exit_at = None
    row.last_checked_at = now


def list_user_universes(db: Session, user_id: int, status: str = "active") -> list[dict[str, Any]]:
    q = db.query(TrackPosition.universe).filter(TrackPosition.user_id == user_id)
    if status == "active":
        q = q.filter(TrackPosition.status == ACTIVE_STATUS)
    elif status == "closed":
        q = q.filter(TrackPosition.status != ACTIVE_STATUS)
    rows = q.distinct().all()
    out = []
    for (universe,) in sorted(rows, key=lambda x: x[0]):
        out.append(
            {
                "id": universe,
                "label": UNIVERSE_LABELS.get(universe, universe.upper()),
            }
        )
    return out


def get_benchmark_summaries(
    db: Session,
    user_id: int,
    status: str = "active",
) -> dict[str, dict[str, Any]]:
    """Per-universe benchmark change since earliest tracked position entry."""
    q = db.query(TrackPosition).filter(TrackPosition.user_id == user_id)
    if status == "active":
        q = q.filter(TrackPosition.status == ACTIVE_STATUS)
    elif status == "closed":
        q = q.filter(TrackPosition.status != ACTIVE_STATUS)
    rows = q.all()
    if not rows:
        return {}

    by_universe: dict[str, list[TrackPosition]] = {}
    for row in rows:
        by_universe.setdefault(row.universe, []).append(row)

    summaries: dict[str, dict[str, Any]] = {}
    for universe, group in by_universe.items():
        meta = benchmark_meta(universe)
        if not meta:
            continue

        earliest = min(group, key=lambda r: r.entry_at)
        ref_px = earliest.benchmark_entry_price
        label = earliest.benchmark_symbol or meta["label"]

        latest_log = (
            db.query(TrackBenchmarkLog)
            .filter(TrackBenchmarkLog.universe == universe)
            .order_by(TrackBenchmarkLog.recorded_at.desc())
            .first()
        )
        current_px = latest_log.price if latest_log else None
        if ref_px is None and latest_log:
            first_log = (
                db.query(TrackBenchmarkLog)
                .filter(
                    TrackBenchmarkLog.universe == universe,
                    TrackBenchmarkLog.recorded_at >= earliest.entry_at,
                )
                .order_by(TrackBenchmarkLog.recorded_at.asc())
                .first()
            )
            if first_log:
                ref_px = first_log.price

        change_pct = pct_change(ref_px, current_px) if ref_px and current_px else None
        summaries[universe] = {
            "label": label,
            "symbol": meta["symbol"],
            "reference_price": ref_px,
            "current_price": current_px,
            "change_pct": change_pct,
            "updated_at": utc_iso(latest_log.recorded_at) if latest_log else None,
            "reference_at": utc_iso(earliest.entry_at),
        }
    return summaries


def get_price_history(db: Session, user_id: int, position_id: int) -> dict[str, Any]:
    row = (
        db.query(TrackPosition)
        .filter(TrackPosition.id == position_id, TrackPosition.user_id == user_id)
        .first()
    )
    if not row:
        raise ValueError("İzleme kaydı bulunamadı")

    logs = (
        db.query(TrackPriceLog)
        .filter(TrackPriceLog.position_id == position_id)
        .order_by(TrackPriceLog.recorded_at.asc())
        .all()
    )

    points: list[dict[str, Any]] = []
    if not logs:
        points.append(
            {
                "recorded_at": utc_iso(row.entry_at),
                "price": row.entry_price,
                "change_pct": 0.0,
            }
        )
        if row.current_price is not None and row.current_price != row.entry_price:
            ts = row.last_checked_at or row.exit_at or row.entry_at
            points.append(
                {
                    "recorded_at": utc_iso(ts),
                    "price": row.current_price,
                    "change_pct": pct_change(row.entry_price, row.current_price),
                }
            )
    else:
        for log in logs:
            points.append(
                {
                    "recorded_at": utc_iso(log.recorded_at),
                    "price": log.price,
                    "change_pct": pct_change(row.entry_price, log.price),
                }
            )

    target_pct = pct_change(row.entry_price, row.target_price)
    stop_pct = pct_change(row.entry_price, row.stop_price)
    benchmark_points = _benchmark_points_for_position(db, row)
    benchmark_aligned = _align_benchmark_to_stock(points, benchmark_points)
    meta = benchmark_meta(row.universe)

    return {
        "position_id": row.id,
        "symbol": row.symbol,
        "universe": row.universe,
        "source_label": row.source_label,
        "timeframe": row.timeframe,
        "status": row.status,
        "entry_price": row.entry_price,
        "entry_at": utc_iso(row.entry_at),
        "target_price": row.target_price,
        "stop_price": row.stop_price,
        "target_pct": target_pct,
        "stop_pct": stop_pct,
        "benchmark_label": row.benchmark_symbol or (meta["label"] if meta else None),
        "benchmark_entry_price": row.benchmark_entry_price,
        "benchmark_points": benchmark_points,
        "benchmark_aligned": benchmark_aligned,
        "timezone": DEFAULT_SCHEDULE_TIMEZONE,
        "points": points,
    }


def update_active_prices(db: Session, user_id: int | None = None) -> dict[str, int]:
    q = db.query(TrackPosition).filter(TrackPosition.status == ACTIVE_STATUS)
    if user_id is not None:
        q = q.filter(TrackPosition.user_id == user_id)
    rows = q.all()
    if not rows:
        return {"checked": 0, "closed": 0}

    by_universe: dict[str, list[TrackPosition]] = {}
    for row in rows:
        by_universe.setdefault(row.universe, []).append(row)

    now = datetime.now(timezone.utc)
    closed = 0
    checked = 0
    universe_keys = list(by_universe.keys())
    benchmark_prices = fetch_benchmark_prices(universe_keys)

    for universe, group in by_universe.items():
        bm_px = benchmark_prices.get(universe)
        if bm_px is not None:
            log_benchmark(db, universe, bm_px, at=now)

        symbols = list({r.symbol for r in group})
        prices = fetch_latest_prices(symbols, universe)
        for row in group:
            if bm_px is not None:
                _ensure_position_benchmark(db, row, universe, bm_px)

            price = prices.get(row.symbol)
            if price is None:
                continue
            checked += 1
            row.current_price = price
            row.last_checked_at = now
            log_price(db, row.id, price, at=now)

            settings = get_or_create_settings(db, row.user_id)
            if settings.auto_close_on_tp_sl:
                if price >= row.target_price:
                    _close_position(row, reason="hit_target", exit_price=price, now=now)
                    closed += 1
                elif price <= row.stop_price:
                    _close_position(row, reason="hit_stop", exit_price=price, now=now)
                    closed += 1

    db.commit()
    return {"checked": checked, "closed": closed}


def enrich_positions_benchmarks(db: Session, rows: list[TrackPosition]) -> None:
    """Backfill per-position benchmark fields from stored logs."""
    updated = False
    for row in rows:
        if row.benchmark_current_price is not None and row.benchmark_entry_price is not None:
            continue
        latest_log = (
            db.query(TrackBenchmarkLog)
            .filter(
                TrackBenchmarkLog.universe == row.universe,
                TrackBenchmarkLog.recorded_at >= row.entry_at,
            )
            .order_by(TrackBenchmarkLog.recorded_at.desc())
            .first()
        )
        if latest_log:
            _ensure_position_benchmark(db, row, row.universe, latest_log.price)
            updated = True
    if updated:
        db.commit()


def maybe_weekend_expire(db: Session) -> int:
    """Optional auto-expire intraday tracks (off by default)."""
    now = datetime.now(timezone.utc)
    if now.weekday() != 4:
        return 0

    settings_rows = (
        db.query(TrackUserSettings)
        .filter(TrackUserSettings.auto_close_weekend_intraday.is_(True))
        .all()
    )
    if not settings_rows:
        return 0

    expired = 0
    for settings in settings_rows:
        rows = (
            db.query(TrackPosition)
            .filter(
                TrackPosition.user_id == settings.user_id,
                TrackPosition.status == ACTIVE_STATUS,
                TrackPosition.timeframe.in_(list(INTRADAY_TIMEFRAMES)),
            )
            .all()
        )
        for row in rows:
            _close_position(row, reason="expired", exit_price=row.current_price, now=now)
            expired += 1

    if expired:
        db.commit()
    return expired


def manual_close(db: Session, user_id: int, position_id: int) -> TrackPosition:
    row = (
        db.query(TrackPosition)
        .filter(TrackPosition.id == position_id, TrackPosition.user_id == user_id)
        .first()
    )
    if not row:
        raise ValueError("İzleme kaydı bulunamadı")
    if row.status != ACTIVE_STATUS:
        raise ValueError("Kayıt zaten kapalı")
    now = datetime.now(timezone.utc)
    exit_px = row.current_price
    if exit_px is not None:
        log_price(db, row.id, exit_px, at=now)
    bm_px = fetch_benchmark_price(row.universe)
    if bm_px is not None:
        log_benchmark(db, row.universe, bm_px, at=now)
        _ensure_position_benchmark(db, row, row.universe, bm_px)
    _close_position(row, reason="manual_close", exit_price=exit_px, now=now)
    db.commit()
    db.refresh(row)
    return row


def clear_active(db: Session, user_id: int) -> int:
    rows = (
        db.query(TrackPosition.id)
        .filter(TrackPosition.user_id == user_id, TrackPosition.status == ACTIVE_STATUS)
        .all()
    )
    ids = [r[0] for r in rows]
    return close_positions_by_ids(db, user_id, ids)


def close_positions_by_ids(db: Session, user_id: int, position_ids: list[int]) -> int:
    if not position_ids:
        return 0
    now = datetime.now(timezone.utc)
    rows = (
        db.query(TrackPosition)
        .filter(
            TrackPosition.user_id == user_id,
            TrackPosition.id.in_(position_ids),
            TrackPosition.status == ACTIVE_STATUS,
        )
        .all()
    )
    if not rows:
        return 0

    universes = list({r.universe for r in rows})
    benchmark_prices = fetch_benchmark_prices(universes)
    for row in rows:
        exit_px = row.current_price
        if exit_px is not None:
            log_price(db, row.id, exit_px, at=now)
        bm_px = benchmark_prices.get(row.universe)
        if bm_px is not None:
            log_benchmark(db, row.universe, bm_px, at=now)
            _ensure_position_benchmark(db, row, row.universe, bm_px)
        _close_position(row, reason="manual_close", exit_price=exit_px, now=now)
    db.commit()
    return len(rows)


def reopen_positions_by_ids(db: Session, user_id: int, position_ids: list[int]) -> int:
    if not position_ids:
        return 0
    now = datetime.now(timezone.utc)
    rows = (
        db.query(TrackPosition)
        .filter(
            TrackPosition.user_id == user_id,
            TrackPosition.id.in_(position_ids),
            TrackPosition.status != ACTIVE_STATUS,
        )
        .all()
    )
    if not rows:
        return 0

    by_universe: dict[str, list[TrackPosition]] = {}
    for row in rows:
        by_universe.setdefault(row.universe, []).append(row)

    for universe, group in by_universe.items():
        symbols = list({r.symbol for r in group})
        prices = fetch_latest_prices(symbols, universe)
        bm_px = fetch_benchmark_price(universe)
        if bm_px is not None:
            log_benchmark(db, universe, bm_px, at=now)
        for row in group:
            price = prices.get(row.symbol)
            if price is not None:
                row.current_price = price
                log_price(db, row.id, price, at=now)
            elif row.exit_price is not None:
                row.current_price = row.exit_price
            if bm_px is not None:
                _ensure_position_benchmark(db, row, universe, bm_px)
            _reopen_position(row, now)

    db.commit()
    return len(rows)


def delete_closed_positions_by_ids(db: Session, user_id: int, position_ids: list[int]) -> int:
    if not position_ids:
        return 0
    rows = (
        db.query(TrackPosition)
        .filter(
            TrackPosition.user_id == user_id,
            TrackPosition.id.in_(position_ids),
            TrackPosition.status != ACTIVE_STATUS,
        )
        .all()
    )
    if not rows:
        return 0
    ids = [r.id for r in rows]
    db.query(TrackPriceLog).filter(TrackPriceLog.position_id.in_(ids)).delete(synchronize_session=False)
    for row in rows:
        db.delete(row)
    db.commit()
    return len(ids)
