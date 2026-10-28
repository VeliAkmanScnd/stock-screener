"""Market Bias optimizer API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth_deps import get_current_user
from app.database import User
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
