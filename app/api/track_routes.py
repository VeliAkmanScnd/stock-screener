"""Performance tracking API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth_deps import get_current_user
from app.database import TrackPosition, User, get_db
from app.services.track_service import (
    ACTIVE_STATUS,
    calc_levels,
    clear_active,
    close_positions_by_ids,
    enrich_positions_benchmarks,
    get_benchmark_summaries,
    get_or_create_settings,
    get_price_history,
    ingest_scan_results,
    list_user_universes,
    manual_close,
    position_to_dict,
    reopen_positions_by_ids,
    delete_closed_positions_by_ids,
    update_active_prices,
)
from app.utils.datetime_fmt import utc_iso

router = APIRouter(prefix="/api/track", tags=["track"])


class TrackSettingsUpdate(BaseModel):
    target_pct: float | None = Field(default=None, ge=0.1, le=100)
    stop_pct: float | None = Field(default=None, ge=0.1, le=100)
    auto_track_enabled: bool | None = None
    auto_close_on_tp_sl: bool | None = None
    auto_close_weekend_intraday: bool | None = None
    weekend_close_hour: int | None = Field(default=None, ge=0, le=23)


class TrackPositionUpdate(BaseModel):
    target_price: float | None = Field(default=None, gt=0)
    stop_price: float | None = Field(default=None, gt=0)
    target_pct: float | None = Field(default=None, ge=0.1, le=100)
    stop_pct: float | None = Field(default=None, ge=0.1, le=100)


class TrackIngestBody(BaseModel):
    universe: str
    timeframe: str = "1d"
    source_label: str = "Manuel tarama"
    results: list[dict[str, Any]]


class TrackBulkIdsBody(BaseModel):
    position_ids: list[int] = Field(min_length=1)


def _settings_dict(row) -> dict[str, Any]:
    return {
        "target_pct": row.target_pct,
        "stop_pct": row.stop_pct,
        "auto_track_enabled": row.auto_track_enabled,
        "auto_close_on_tp_sl": row.auto_close_on_tp_sl,
        "auto_close_weekend_intraday": row.auto_close_weekend_intraday,
        "weekend_close_hour": row.weekend_close_hour,
        "updated_at": utc_iso(row.updated_at),
    }


@router.get("/settings")
def get_settings(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _settings_dict(get_or_create_settings(db, user.id))


@router.patch("/settings")
def patch_settings(
    body: TrackSettingsUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = get_or_create_settings(db, user.id)
    if body.target_pct is not None:
        row.target_pct = body.target_pct
    if body.stop_pct is not None:
        row.stop_pct = body.stop_pct
    if body.auto_track_enabled is not None:
        row.auto_track_enabled = body.auto_track_enabled
    if body.auto_close_on_tp_sl is not None:
        row.auto_close_on_tp_sl = body.auto_close_on_tp_sl
    if body.auto_close_weekend_intraday is not None:
        row.auto_close_weekend_intraday = body.auto_close_weekend_intraday
    if body.weekend_close_hour is not None:
        row.weekend_close_hour = body.weekend_close_hour
    db.commit()
    db.refresh(row)
    return _settings_dict(row)


@router.get("/universes")
def list_universes(
    status: str = "active",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    universes = list_user_universes(db, user.id, status=status)
    summaries = get_benchmark_summaries(db, user.id, status=status)
    for item in universes:
        item["benchmark"] = summaries.get(item["id"])
    return universes


@router.get("/benchmarks")
def list_benchmarks(
    status: str = "active",
    universe: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    summaries = get_benchmark_summaries(db, user.id, status=status)
    if universe and universe != "all":
        row = summaries.get(universe)
        if not row:
            raise HTTPException(404, "Endeks verisi bulunamadı")
        return row
    return summaries


@router.get("/positions")
def list_positions(
    status: str = "active",
    universe: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(TrackPosition).filter(TrackPosition.user_id == user.id)
    if status == "active":
        q = q.filter(TrackPosition.status == ACTIVE_STATUS)
    elif status == "closed":
        q = q.filter(TrackPosition.status != ACTIVE_STATUS)
    if universe and universe != "all":
        q = q.filter(TrackPosition.universe == universe)
    rows = q.order_by(TrackPosition.entry_at.desc()).limit(500).all()
    enrich_positions_benchmarks(db, rows)
    return [position_to_dict(r) for r in rows]


@router.get("/positions/{position_id}/history")
def position_history(
    position_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        return get_price_history(db, user.id, position_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/positions/ingest")
def ingest_manual(
    body: TrackIngestBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    payload = {
        "universe": body.universe,
        "timeframe": body.timeframe,
        "results": body.results,
    }
    added = ingest_scan_results(
        db,
        user_id=user.id,
        payload=payload,
        source_type="manual",
        source_label=body.source_label,
    )
    return {"ok": True, "added": added}


@router.patch("/positions/{position_id}")
def update_position(
    position_id: int,
    body: TrackPositionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = (
        db.query(TrackPosition)
        .filter(TrackPosition.id == position_id, TrackPosition.user_id == user.id)
        .first()
    )
    if not row:
        raise HTTPException(404, "İzleme kaydı bulunamadı")
    if row.status != ACTIVE_STATUS:
        raise HTTPException(400, "Kapalı kayıt düzenlenemez")

    if body.target_pct is not None:
        row.target_pct = body.target_pct
        row.target_price = calc_levels(row.entry_price, row.target_pct, row.stop_pct)[0]
    if body.stop_pct is not None:
        row.stop_pct = body.stop_pct
        row.stop_price = calc_levels(row.entry_price, row.target_pct, row.stop_pct)[1]
    if body.target_price is not None:
        row.target_price = body.target_price
        row.target_pct = round((row.target_price / row.entry_price - 1) * 100, 2)
    if body.stop_price is not None:
        row.stop_price = body.stop_price
        row.stop_pct = round((1 - row.stop_price / row.entry_price) * 100, 2)

    db.commit()
    db.refresh(row)
    return position_to_dict(row)


@router.post("/positions/{position_id}/close")
def close_position(
    position_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        row = manual_close(db, user.id, position_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return position_to_dict(row)


@router.post("/positions/bulk-close")
def bulk_close_positions(
    body: TrackBulkIdsBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    count = close_positions_by_ids(db, user.id, body.position_ids)
    return {"ok": True, "closed": count}


@router.post("/positions/bulk-reopen")
def bulk_reopen_positions(
    body: TrackBulkIdsBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    count = reopen_positions_by_ids(db, user.id, body.position_ids)
    return {"ok": True, "reopened": count}


@router.post("/positions/bulk-delete")
def bulk_delete_positions(
    body: TrackBulkIdsBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    count = delete_closed_positions_by_ids(db, user.id, body.position_ids)
    return {"ok": True, "deleted": count}


@router.post("/positions/clear-active")
def clear_active_positions(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    count = clear_active(db, user.id)
    return {"ok": True, "closed": count}


@router.post("/refresh-prices")
def refresh_prices(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stats = update_active_prices(db, user.id)
    return stats
