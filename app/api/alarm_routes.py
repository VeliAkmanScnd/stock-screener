"""VIOP pay alarm CRUD — stored as scheduled scans with alarm=true."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth_deps import get_current_user
from app.api.schedule_routes import (
    _get_owned,
    _row_to_dict,
    _row_weekdays,
    _validate_schedule_fields,
    run_scheduled_now,
)
from app.config import DEFAULT_SCHEDULE_TIMEZONE
from app.database import ScanRun, ScheduledScan, User, get_db
from app.services.alarm_service import (
    ALARM_TIMEFRAMES,
    alarm_view,
    build_scan_config,
    config_from_row,
    is_alarm_config,
    list_viop_pay_contracts,
    parse_contracts,
)
from app.services.scan_executor import config_to_json
from app.services.schedule_helpers import (
    normalize_schedule_type,
    weekdays_to_storage,
)
from app.services.scheduler import register_job, unregister_job

router = APIRouter(prefix="/api/alarms", tags=["alarms"])
logger = logging.getLogger(__name__)


class AlarmBody(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    pine_script_id: int
    pine_input_overrides: dict[str, Any] = Field(default_factory=dict)
    contracts: list[str] = Field(min_length=1)
    timeframe: str = "15m"
    hour: int = Field(default=9, ge=0, le=23)
    minute: int = Field(default=1, ge=0, le=59)
    end_hour: int = Field(default=18, ge=0, le=23)
    weekdays: list[int] | None = None
    telegram_to: str | None = None
    telegram_bot_token: str | None = None
    notify_telegram: bool = True
    enabled: bool = True


class AlarmPatch(BaseModel):
    name: str | None = None
    pine_script_id: int | None = None
    pine_input_overrides: dict[str, Any] | None = None
    contracts: list[str] | None = None
    timeframe: str | None = None
    hour: int | None = Field(default=None, ge=0, le=23)
    minute: int | None = Field(default=None, ge=0, le=59)
    end_hour: int | None = Field(default=None, ge=0, le=23)
    weekdays: list[int] | None = None
    telegram_to: str | None = None
    telegram_bot_token: str | None = None
    notify_telegram: bool | None = None
    enabled: bool | None = None


def _weekdays(days: list[int] | None) -> list[int]:
    vals = sorted(set(int(d) for d in (days or [0, 1, 2, 3, 4])))
    for d in vals:
        if d < 0 or d > 6:
            raise HTTPException(400, "Gün 0–6 arasında olmalı.")
    return vals or [0, 1, 2, 3, 4]


def _tf(value: str | None) -> str:
    tf = normalize_schedule_type(value or "15m")
    if tf not in ALARM_TIMEFRAMES:
        raise HTTPException(400, "Alarm periyodu 3m, 5m, 15m, 30m veya 1h olmalı.")
    return tf


@router.get("/contracts")
def alarm_contracts(_user: User = Depends(get_current_user)):
    rows = list_viop_pay_contracts()
    return {"count": len(rows), "contracts": rows}


@router.get("")
def list_alarms(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(ScheduledScan)
    if user.role != "admin":
        q = q.filter(ScheduledScan.user_id == user.id)
    rows = q.order_by(ScheduledScan.created_at.desc()).all()
    out = []
    for row in rows:
        try:
            if not is_alarm_config(config_from_row(row)):
                continue
            out.append(alarm_view(_row_to_dict(row)))
        except Exception:
            logger.exception("Alarm listesi satırı atlandı id=%s", getattr(row, "id", None))
    return out


@router.get("/{alarm_id}")
def get_alarm(
    alarm_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = _get_owned(db, alarm_id, user)
    if not is_alarm_config(config_from_row(row)):
        raise HTTPException(404, "Alarm bulunamadı")
    return alarm_view(_row_to_dict(row))


@router.post("")
def create_alarm(
    body: AlarmBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tf = _tf(body.timeframe)
    contracts = parse_contracts(body.contracts)
    if not contracts:
        raise HTTPException(400, "En az bir VIOP pay kontratı seçin.")
    weekdays = _weekdays(body.weekdays)
    _validate_schedule_fields(tf, None, weekdays, body.hour, body.end_hour)
    cfg = build_scan_config(
        pine_script_id=body.pine_script_id,
        pine_input_overrides=body.pine_input_overrides,
        contracts=contracts,
        timeframe=tf,
        telegram_to=body.telegram_to,
        telegram_bot_token=(body.telegram_bot_token or "").strip() or None,
    )
    row = ScheduledScan(
        user_id=user.id,
        name=body.name.strip(),
        config_json=config_to_json(cfg),
        schedule_type=tf,
        hour=body.hour,
        minute=body.minute,
        end_hour=body.end_hour,
        weekdays=weekdays_to_storage(weekdays),
        timezone=DEFAULT_SCHEDULE_TIMEZONE,
        email_to="",
        telegram_to=body.telegram_to,
        telegram_bot_token=(body.telegram_bot_token or "").strip() or None,
        notify_email=False,
        notify_telegram=bool(body.notify_telegram),
        enabled=body.enabled,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    if row.enabled:
        register_job(row)
    return alarm_view(_row_to_dict(row))


@router.patch("/{alarm_id}")
def update_alarm(
    alarm_id: int,
    body: AlarmPatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = _get_owned(db, alarm_id, user)
    cfg = config_from_row(row)
    if not is_alarm_config(cfg):
        raise HTTPException(404, "Alarm bulunamadı")
    if body.name is not None:
        row.name = body.name.strip()
    if body.hour is not None:
        row.hour = body.hour
    if body.minute is not None:
        row.minute = body.minute
    if body.end_hour is not None:
        row.end_hour = body.end_hour
    if body.weekdays is not None:
        row.weekdays = weekdays_to_storage(_weekdays(body.weekdays))
    if body.telegram_to is not None:
        row.telegram_to = body.telegram_to
    if body.telegram_bot_token is not None:
        token = (body.telegram_bot_token or "").strip()
        if token:
            row.telegram_bot_token = token
    if body.notify_telegram is not None:
        row.notify_telegram = body.notify_telegram
    if body.enabled is not None:
        row.enabled = body.enabled

    tf = _tf(body.timeframe or cfg.get("timeframe") or row.schedule_type)
    pine_id = body.pine_script_id or cfg.get("pine_script_id")
    if not pine_id:
        raise HTTPException(400, "Pine script seçin.")
    contracts = parse_contracts(
        body.contracts if body.contracts is not None else cfg.get("custom_symbols")
    )
    if not contracts:
        raise HTTPException(400, "En az bir VIOP pay kontratı seçin.")
    overrides = (
        body.pine_input_overrides
        if body.pine_input_overrides is not None
        else (cfg.get("pine_input_overrides") or {})
    )
    row.schedule_type = tf
    weekdays = _weekdays(
        body.weekdays if body.weekdays is not None else _row_weekdays(row)
    )
    _validate_schedule_fields(tf, None, weekdays, row.hour, row.end_hour)
    row.config_json = config_to_json(
        build_scan_config(
            pine_script_id=int(pine_id),
            pine_input_overrides=overrides,
            contracts=contracts,
            timeframe=tf,
            telegram_to=row.telegram_to,
            telegram_bot_token=row.telegram_bot_token,
        )
    )
    db.commit()
    db.refresh(row)
    unregister_job(row.id)
    if row.enabled:
        register_job(row)
    return alarm_view(_row_to_dict(row))


@router.delete("/{alarm_id}")
def delete_alarm(
    alarm_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = _get_owned(db, alarm_id, user)
    if not is_alarm_config(config_from_row(row)):
        raise HTTPException(404, "Alarm bulunamadı")
    unregister_job(row.id)
    db.query(ScanRun).filter(ScanRun.scheduled_scan_id == alarm_id).delete()
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/{alarm_id}/run-now")
def run_alarm_now(
    alarm_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = _get_owned(db, alarm_id, user)
    if not is_alarm_config(config_from_row(row)):
        raise HTTPException(404, "Alarm bulunamadı")
    return run_scheduled_now(alarm_id, db, user)
