"""Scheduled scan CRUD and run history."""



from __future__ import annotations



import json

import threading

from datetime import datetime, timezone

from typing import Any



from fastapi import APIRouter, Depends, HTTPException

from fastapi.responses import PlainTextResponse

from pydantic import BaseModel, Field, field_validator

from sqlalchemy.orm import Session



from app.api.auth_deps import get_current_user

from app.api.routes import FilterRuleModel, ScanBody

from app.config import DEFAULT_SCHEDULE_TIMEZONE

from app.database import ScanRun, ScheduledScan, User, get_db

from app.services.email_service import send_tv_list_email, smtp_configured

from app.services.scan_executor import config_to_json, execute_scan_config, scan_body_from_dict

from app.services.schedule_helpers import (
    SCHEDULE_TYPES,
    is_window_schedule_type,
    normalize_email_storage,
    normalize_schedule_type,
    parse_email_list,
    parse_weekdays_field,
    weekdays_to_storage,
)

from app.services.schedule_runner import run_scheduled_scan

from app.services.scheduler import next_run_for_schedule, register_job, scheduler_status, unregister_job

from app.utils.datetime_fmt import utc_iso



router = APIRouter(prefix="/api/scheduled-scans", tags=["scheduled-scans"])



def _validate_weekdays_list(days: list[int] | None) -> list[int] | None:

    if days is None:

        return None

    unique = sorted(set(days))

    for day in unique:

        if day < 0 or day > 6:

            raise ValueError("Gün 0–6 arasında olmalı (0=Pazartesi, 6=Pazar).")

    return unique





class ScheduledScanCreate(BaseModel):

    name: str = Field(min_length=1, max_length=255)

    schedule_type: str = "daily"

    hour: int = Field(default=8, ge=0, le=23)

    minute: int = Field(default=30, ge=0, le=59)

    end_hour: int | None = Field(default=None, ge=0, le=23)

    weekday: int | None = Field(default=None, ge=0, le=6)

    weekdays: list[int] | None = None

    timezone: str = DEFAULT_SCHEDULE_TIMEZONE

    email_to: str

    enabled: bool = True

    scan_config: ScanBody



    @field_validator("email_to")

    @classmethod

    def validate_email_to(cls, value: str) -> str:

        try:

            emails = parse_email_list(value)

        except ValueError as exc:

            raise ValueError(str(exc)) from exc

        if not emails:

            raise ValueError("En az bir e-posta adresi gerekli.")

        return normalize_email_storage(emails)



    @field_validator("weekdays")

    @classmethod

    def validate_weekdays(cls, value: list[int] | None) -> list[int] | None:

        return _validate_weekdays_list(value)





class ScheduledScanUpdate(BaseModel):

    name: str | None = None

    schedule_type: str | None = None

    hour: int | None = Field(default=None, ge=0, le=23)

    minute: int | None = Field(default=None, ge=0, le=59)

    end_hour: int | None = Field(default=None, ge=0, le=23)

    weekday: int | None = Field(default=None, ge=0, le=6)

    weekdays: list[int] | None = None

    timezone: str | None = None

    email_to: str | None = None

    enabled: bool | None = None

    scan_config: ScanBody | None = None



    @field_validator("email_to")

    @classmethod

    def validate_email_to(cls, value: str | None) -> str | None:

        if value is None:

            return None

        try:

            emails = parse_email_list(value)

        except ValueError as exc:

            raise ValueError(str(exc)) from exc

        if not emails:

            raise ValueError("En az bir e-posta adresi gerekli.")

        return normalize_email_storage(emails)



    @field_validator("weekdays")

    @classmethod

    def validate_weekdays(cls, value: list[int] | None) -> list[int] | None:

        return _validate_weekdays_list(value)





def _row_weekdays(row: ScheduledScan) -> list[int]:

    if row.weekdays:

        return parse_weekdays_field(row.weekdays)

    if normalize_schedule_type(row.schedule_type) == "1wk" and row.weekday is not None:

        return [int(row.weekday)]

    return []





def _row_to_dict(row: ScheduledScan, *, owner_username: str | None = None) -> dict[str, Any]:

    return {

        "id": row.id,

        "user_id": row.user_id,

        "owner_username": owner_username,

        "name": row.name,

        "schedule_type": row.schedule_type,

        "hour": row.hour,

        "minute": row.minute,

        "end_hour": row.end_hour,

        "weekday": row.weekday,

        "weekdays": _row_weekdays(row),

        "timezone": row.timezone,

        "email_to": row.email_to,

        "enabled": row.enabled,

        "last_run_at": utc_iso(row.last_run_at),

        "next_run_at": utc_iso(next_run_for_schedule(row)),

        "last_status": row.last_status,

        "last_match_count": row.last_match_count,

        "last_error": row.last_error,

        "scan_config": json.loads(row.config_json),

        "created_at": utc_iso(row.created_at),

    }





def _get_owned(db: Session, scan_id: int, user: User) -> ScheduledScan:

    row = db.query(ScheduledScan).filter(ScheduledScan.id == scan_id).first()

    if not row:

        raise HTTPException(404, "Zamanlanmış tarama bulunamadı")

    if row.user_id != user.id and user.role != "admin":

        raise HTTPException(404, "Zamanlanmış tarama bulunamadı")

    return row





def _validate_schedule_fields(
    schedule_type: str,
    weekday: int | None,
    weekdays: list[int] | None,
    hour: int,
    end_hour: int | None,
) -> None:

    canon = normalize_schedule_type(schedule_type)
    if canon == "1wk" and weekday is None and not weekdays:
        raise HTTPException(400, "Haftalık tarama için en az bir gün seçin.")
    if canon == "1d" and not weekdays:
        raise HTTPException(400, "Günlük tarama için en az bir gün seçin.")
    if is_window_schedule_type(canon):
        if end_hour is None:
            raise HTTPException(400, "Bu periyot için bitiş saati gerekli (ör. 18).")
        if end_hour < hour:
            raise HTTPException(400, "Bitiş saati başlangıç saatinden önce olamaz.")





@router.get("/config")

def schedule_config():

    return {

        "smtp_configured": smtp_configured(),

        "default_timezone": DEFAULT_SCHEDULE_TIMEZONE,

        "scheduler": scheduler_status(),

        "schedule_types": [
            {"id": "1d", "label": "Günlük (1D)"},
            {"id": "1wk", "label": "Haftalık (1W)"},
            {"id": "12h", "label": "12 saat"},
            {"id": "8h", "label": "8 saat"},
            {"id": "4h", "label": "4 saat"},
            {"id": "2h", "label": "2 saat (2H)"},
            {"id": "1h", "label": "Saatlik (1H)"},
            {"id": "30m", "label": "30 dakika"},
            {"id": "15m", "label": "15 dakika"},
            {"id": "5m", "label": "5 dakika"},
        ],

    }





@router.get("")

def list_scheduled_scans(

    db: Session = Depends(get_db),

    user: User = Depends(get_current_user),

):

    q = db.query(ScheduledScan)
    if user.role != "admin":
        q = q.filter(ScheduledScan.user_id == user.id)
    rows = q.order_by(ScheduledScan.created_at.desc()).all()
    owner_ids = {r.user_id for r in rows}
    owners = (
        {
            u.id: u.username
            for u in db.query(User).filter(User.id.in_(owner_ids)).all()
        }
        if owner_ids
        else {}
    )
    return [_row_to_dict(r, owner_username=owners.get(r.user_id)) for r in rows]





@router.get("/{scan_id}")
def get_scheduled_scan(
    scan_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = _get_owned(db, scan_id, user)
    return _row_to_dict(row)





@router.post("")

def create_scheduled_scan(

    body: ScheduledScanCreate,

    db: Session = Depends(get_db),

    user: User = Depends(get_current_user),

):

    if body.schedule_type not in SCHEDULE_TYPES:

        raise HTTPException(400, "Geçersiz schedule_type")

    _validate_schedule_fields(body.schedule_type, body.weekday, body.weekdays, body.hour, body.end_hour)



    weekdays_str = weekdays_to_storage(body.weekdays) if body.weekdays else None



    row = ScheduledScan(

        user_id=user.id,

        name=body.name.strip(),

        config_json=config_to_json(body.scan_config.model_dump()),

        schedule_type=normalize_schedule_type(body.schedule_type),

        hour=body.hour,

        minute=body.minute,

        end_hour=body.end_hour,

        weekday=body.weekday,

        weekdays=weekdays_str,

        timezone=body.timezone or DEFAULT_SCHEDULE_TIMEZONE,

        email_to=body.email_to,

        enabled=body.enabled,

    )

    db.add(row)

    db.commit()

    db.refresh(row)

    if row.enabled:

        register_job(row)

    return _row_to_dict(row)





@router.patch("/{scan_id}")

def update_scheduled_scan(

    scan_id: int,

    body: ScheduledScanUpdate,

    db: Session = Depends(get_db),

    user: User = Depends(get_current_user),

):

    row = _get_owned(db, scan_id, user)

    if body.name is not None:

        row.name = body.name.strip()

    if body.schedule_type is not None:

        if body.schedule_type not in SCHEDULE_TYPES:

            raise HTTPException(400, "Geçersiz schedule_type")

        row.schedule_type = normalize_schedule_type(body.schedule_type)

    if body.hour is not None:

        row.hour = body.hour

    if body.minute is not None:

        row.minute = body.minute

    if "end_hour" in body.model_fields_set:

        row.end_hour = body.end_hour

    if body.weekday is not None:

        row.weekday = body.weekday

    if body.weekdays is not None:

        row.weekdays = weekdays_to_storage(body.weekdays) if body.weekdays else None

    if body.timezone is not None:

        row.timezone = body.timezone

    if body.email_to is not None:

        row.email_to = body.email_to

    if body.enabled is not None:

        row.enabled = body.enabled

    if body.scan_config is not None:

        row.config_json = config_to_json(body.scan_config.model_dump())

    _validate_schedule_fields(
        row.schedule_type,
        row.weekday,
        _row_weekdays(row),
        row.hour,
        row.end_hour,
    )

    db.commit()

    db.refresh(row)

    unregister_job(row.id)

    if row.enabled:

        register_job(row)

    return _row_to_dict(row)





@router.delete("/{scan_id}")

def delete_scheduled_scan(

    scan_id: int,

    db: Session = Depends(get_db),

    user: User = Depends(get_current_user),

):

    row = _get_owned(db, scan_id, user)

    unregister_job(row.id)

    db.query(ScanRun).filter(ScanRun.scheduled_scan_id == scan_id).delete()

    db.delete(row)

    db.commit()

    return {"ok": True}





@router.post("/{scan_id}/run-now")

def run_scheduled_now(

    scan_id: int,

    db: Session = Depends(get_db),

    user: User = Depends(get_current_user),

):

    _get_owned(db, scan_id, user)

    threading.Thread(
        target=run_scheduled_scan, args=(scan_id,), kwargs={"force": True}, daemon=True
    ).start()

    return {"ok": True, "message": "Tarama arka planda başlatıldı."}





@router.get("/{scan_id}/runs")

def list_scan_runs(

    scan_id: int,

    db: Session = Depends(get_db),

    user: User = Depends(get_current_user),

):

    _get_owned(db, scan_id, user)

    runs = (

        db.query(ScanRun)

        .filter(ScanRun.scheduled_scan_id == scan_id)

        .order_by(ScanRun.started_at.desc())

        .limit(20)

        .all()

    )

    return [

        {

            "id": r.id,

            "started_at": utc_iso(r.started_at),

            "finished_at": utc_iso(r.finished_at),

            "status": r.status,

            "match_count": r.match_count,

            "email_sent": r.email_sent,

            "error_message": r.error_message,

        }

        for r in runs

    ]





@router.get("/{scan_id}/runs/{run_id}/tv")

def download_run_tv_list(

    scan_id: int,

    run_id: int,

    db: Session = Depends(get_db),

    user: User = Depends(get_current_user),

):

    _get_owned(db, scan_id, user)

    run = (

        db.query(ScanRun)

        .filter(ScanRun.id == run_id, ScanRun.scheduled_scan_id == scan_id)

        .first()

    )

    if not run:

        raise HTTPException(404, "Çalıştırma kaydı bulunamadı")

    return PlainTextResponse(run.tv_list_text or "", media_type="text/plain")


class TestEmailBody(BaseModel):
    email_to: str

    @field_validator("email_to")
    @classmethod
    def validate_email_to(cls, value: str) -> str:
        try:
            emails = parse_email_list(value)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        if not emails:
            raise ValueError("En az bir e-posta adresi gerekli.")
        return normalize_email_storage(emails)


@router.post("/test-email")
def test_schedule_email(
    body: TestEmailBody,
    user: User = Depends(get_current_user),
):
    if not smtp_configured():
        raise HTTPException(
            400,
            "SMTP yapılandırılmamış. .env dosyasına SMTP_HOST ve SMTP_FROM ekleyin, uygulamayı yeniden başlatın.",
        )
    try:
        send_tv_list_email(
            to_address=body.email_to,
            subject="TradeLABtr — SMTP test",
            body_text="Bu bir test e-postasıdır. SMTP ayarlarınız çalışıyor.",
            tv_list_text="# test\nBINANCE:BTCUSDT\n",
            filename="smtp_test.txt",
        )
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc
    return {"ok": True, "message": "Test e-postası gönderildi."}

