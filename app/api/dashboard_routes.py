"""Daily scan dashboard."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.auth_deps import get_current_user
from app.database import User, get_db
from app.services.dashboard import build_today_dashboard

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/today")
def dashboard_today(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return build_today_dashboard(db, user)
