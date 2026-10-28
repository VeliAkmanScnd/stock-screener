"""Market Bias optimizer API."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth_deps import get_current_user
from app.database import OptimizePreset, User, get_db
from app.services.alarm_service import list_viop_pay_contracts
from app.services.borsapy_client import tradingview_auth_configured

router = APIRouter(prefix="/api/optimize", tags=["optimize"])


class OptimizeBody(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    timeframe: str = "15m"
    period: str = "60d"
    mode: str = "quick"
    side: str = "both"
    min_win_rate: float = 40
    max_drawdown: float = 20
    min_profit_factor: float = 1.2
    min_profit: float = 5
    min_trades: int = Field(default=8, ge=1, le=500)
    max_combos: int = Field(default=180, ge=20, le=800)
    ha_len: Any = None
    ha_len2: Any = None
    osc_len: Any = None
    ha_htf: Any = None
    exit_mode: Any = None
    rr_mult: Any = None
    swing_bars: Any = None
    tp_pct: Any = None
    sl_pct: Any = None
    reverse_exit: Any = None
    require_bar: Any = None
    max_same: Any = None
    optimize: dict[str, bool] | None = None
    reference: dict[str, Any] | None = None


class PresetBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    symbol: str = ""
    config: dict[str, Any] = Field(default_factory=dict)


def _preset_dict(row: OptimizePreset) -> dict[str, Any]:
    try:
        config = json.loads(row.config_json or "{}")
    except json.JSONDecodeError:
        config = {}
    return {
        "id": row.id,
        "name": row.name,
        "symbol": row.symbol or "",
        "config": config,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _owned_preset(db: Session, preset_id: int, user: User) -> OptimizePreset:
    q = db.query(OptimizePreset).filter(OptimizePreset.id == preset_id)
    if user.role != "admin":
        q = q.filter(OptimizePreset.user_id == user.id)
    row = q.first()
    if not row:
        raise HTTPException(404, "Kayıt bulunamadı")
    return row


@router.get("/contracts")
def optimize_contracts(_user: User = Depends(get_current_user)):
    rows = list_viop_pay_contracts()
    return {
        "count": len(rows),
        "contracts": rows,
        "tv_auth": tradingview_auth_configured(),
    }


@router.post("/bias")
def start_bias_optimize(body: OptimizeBody, _user: User = Depends(get_current_user)):
    from app.services.bias_optimizer import start_optimize_job
    from app.services.borsapy_client import is_borsapy_available

    if not is_borsapy_available():
        raise HTTPException(400, "borsapy yüklü değil")
    if not tradingview_auth_configured():
        raise HTTPException(400, "TradingView sessionid / sessionid_sign .env içinde yok")
    try:
        job_id = start_optimize_job(body.model_dump())
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"job_id": job_id, "status": "running"}


@router.get("/jobs/{job_id}")
def optimize_job(job_id: str, _user: User = Depends(get_current_user)):
    from app.services.bias_optimizer import get_optimize_job

    job = get_optimize_job(job_id)
    if not job:
        raise HTTPException(404, "Test bulunamadı veya süresi doldu")
    return job


@router.get("/presets")
def list_presets(
    symbol: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(OptimizePreset)
    if user.role != "admin":
        q = q.filter(OptimizePreset.user_id == user.id)
    want = (symbol or "").strip().upper()
    if want:
        q = q.filter((OptimizePreset.symbol == want) | (OptimizePreset.symbol == ""))
    rows = q.order_by(OptimizePreset.updated_at.desc()).all()
    return {"count": len(rows), "presets": [_preset_dict(r) for r in rows]}


@router.post("/presets")
def create_preset(
    body: PresetBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Kayıt adı gerekli")
    row = OptimizePreset(
        user_id=user.id,
        name=name,
        symbol=(body.symbol or "").strip().upper(),
        config_json=json.dumps(body.config or {}, ensure_ascii=False),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _preset_dict(row)


@router.put("/presets/{preset_id}")
def update_preset(
    preset_id: int,
    body: PresetBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = _owned_preset(db, preset_id, user)
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Kayıt adı gerekli")
    row.name = name
    row.symbol = (body.symbol or "").strip().upper()
    row.config_json = json.dumps(body.config or {}, ensure_ascii=False)
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return _preset_dict(row)


@router.delete("/presets/{preset_id}")
def delete_preset(
    preset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = _owned_preset(db, preset_id, user)
    db.delete(row)
    db.commit()
    return {"ok": True}
