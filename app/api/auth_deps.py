"""Auth dependencies and session cookies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from app.config import SESSION_COOKIE, SESSION_MAX_AGE_SECONDS, SESSION_SECRET
from app.database import User, get_db
from app.services.auth_service import user_to_dict

_serializer = URLSafeTimedSerializer(SESSION_SECRET, salt="screener-auth")


def create_session_token(user_id: int) -> str:
    return _serializer.dumps({"uid": user_id})


def load_user_id_from_token(token: str) -> int | None:
    try:
        data = _serializer.loads(token, max_age=SESSION_MAX_AGE_SECONDS)
        return int(data.get("uid"))
    except (BadSignature, SignatureExpired, ValueError, TypeError):
        return None


def get_user_from_token(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    uid = load_user_id_from_token(token)
    if uid is None:
        return None
    user = db.query(User).filter(User.id == uid).first()
    if not user or not user.is_active:
        return None
    return user


def get_current_user(
    db: Session = Depends(get_db),
    screener_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> User:
    user = get_user_from_token(db, screener_session)
    if not user:
        raise HTTPException(status_code=401, detail="Oturum gerekli. Lütfen giriş yapın.")
    return user


def get_current_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin yetkisi gerekli.")
    return user


def optional_user(
    db: Session = Depends(get_db),
    screener_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> User | None:
    return get_user_from_token(db, screener_session)


def public_user_dict(user: User) -> dict:
    return user_to_dict(user)
