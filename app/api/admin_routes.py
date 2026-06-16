"""Admin user management API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth_deps import get_current_admin, public_user_dict
from app.database import User, get_db
from app.services.auth_service import create_user, delete_user, list_users, reset_user_password

router = APIRouter(prefix="/api/admin", tags=["admin"])


class CreateUserBody(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=4, description="Geçici şifre; kullanıcı girişte değiştirecek")


class ResetPasswordBody(BaseModel):
    password: str = Field(min_length=4)


@router.get("/users")
def admin_list_users(
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    users = list_users(db)
    return {"users": [public_user_dict(u) for u in users]}


@router.post("/users")
def admin_create_user(
    body: CreateUserBody,
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    try:
        user = create_user(
            db,
            username=body.username,
            password=body.password,
            role="user",
            must_change_password=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "user": public_user_dict(user),
        "message": "Kullanıcı oluşturuldu. İlk girişte şifre değiştirmesi gerekir.",
    }


@router.delete("/users/{user_id}")
def admin_delete_user(
    user_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    try:
        delete_user(db, user_id, actor=admin)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


@router.post("/users/{user_id}/reset-password")
def admin_reset_password(
    user_id: int,
    body: ResetPasswordBody,
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    try:
        user = reset_user_password(db, user_id, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "user": public_user_dict(user),
        "message": "Geçici şifre atandı; kullanıcı tekrar girişte değiştirmeli.",
    }
