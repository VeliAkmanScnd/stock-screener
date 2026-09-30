"""Scan dashboard (day / week / all)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.auth_deps import get_current_user
from app.database import User, get_db
from app.services.dashboard import build_today_dashboard

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/today")
def dashboard_today(
    period: str = Query("day", description="day | week | all"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return build_today_dashboard(db, user, period=period)
