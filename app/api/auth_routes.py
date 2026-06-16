"""Authentication API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth_deps import (
    create_session_token,
    get_current_user,
    public_user_dict,
)
from app.config import SESSION_COOKIE, SESSION_MAX_AGE_SECONDS
from app.database import User, get_db
from app.services.auth_service import authenticate, change_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    username: str
    password: str


class ChangePasswordBody(BaseModel):
    current_password: str | None = None
    new_password: str = Field(min_length=8)


@router.post("/login")
def login(body: LoginBody, response: Response, db: Session = Depends(get_db)):
    user = authenticate(db, body.username, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Kullanıcı adı veya şifre hatalı.")

    token = create_session_token(user.id)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        max_age=SESSION_MAX_AGE_SECONDS,
        samesite="lax",
        path="/",
    )
    return {"user": public_user_dict(user)}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"user": public_user_dict(user)}


@router.post("/change-password")
def change_password_endpoint(
    body: ChangePasswordBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        change_password(
            db,
            user,
            current_password=body.current_password,
            new_password=body.new_password,
            skip_current_check=bool(user.must_change_password),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"user": public_user_dict(user), "message": "Şifre güncellendi."}
