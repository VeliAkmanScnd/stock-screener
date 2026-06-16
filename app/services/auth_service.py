"""User authentication and password policy."""

from __future__ import annotations

import re
from datetime import datetime, timezone

import bcrypt
from sqlalchemy.orm import Session

from app.database import User

PASSWORD_RULES_MSG = (
    "Şifre en az 8 karakter olmalı; büyük harf, küçük harf, rakam ve özel karakter içermelidir."
)

_SPECIAL_RE = re.compile(r"[^A-Za-z0-9]")


def validate_password(password: str) -> tuple[bool, str | None]:
    if len(password) < 8:
        return False, PASSWORD_RULES_MSG
    if not re.search(r"[A-Z]", password):
        return False, PASSWORD_RULES_MSG
    if not re.search(r"[a-z]", password):
        return False, PASSWORD_RULES_MSG
    if not re.search(r"\d", password):
        return False, PASSWORD_RULES_MSG
    if not _SPECIAL_RE.search(password):
        return False, PASSWORD_RULES_MSG
    return True, None


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def user_to_dict(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "must_change_password": bool(user.must_change_password),
        "is_active": bool(user.is_active),
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


def authenticate(db: Session, username: str, password: str) -> User | None:
    user = db.query(User).filter(User.username == username.strip().lower()).first()
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def change_password(
    db: Session,
    user: User,
    *,
    current_password: str | None,
    new_password: str,
    skip_current_check: bool = False,
) -> None:
    ok, msg = validate_password(new_password)
    if not ok:
        raise ValueError(msg or PASSWORD_RULES_MSG)

    if not skip_current_check:
        if not current_password or not verify_password(current_password, user.password_hash):
            raise ValueError("Mevcut şifre hatalı.")

    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    user.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)


def create_user(
    db: Session,
    *,
    username: str,
    password: str,
    role: str = "user",
    must_change_password: bool = True,
) -> User:
    name = username.strip().lower()
    if not name or len(name) < 2:
        raise ValueError("Kullanıcı adı en az 2 karakter olmalıdır.")
    if db.query(User).filter(User.username == name).first():
        raise ValueError("Bu kullanıcı adı zaten kayıtlı.")

    if must_change_password:
        if len(password) < 4:
            raise ValueError("Geçici şifre en az 4 karakter olmalıdır.")
    else:
        ok, msg = validate_password(password)
        if not ok:
            raise ValueError(msg or PASSWORD_RULES_MSG)

    user = User(
        username=name,
        password_hash=hash_password(password),
        role=role,
        must_change_password=must_change_password,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def list_users(db: Session) -> list[User]:
    return db.query(User).order_by(User.username).all()


def delete_user(db: Session, user_id: int, *, actor: User) -> None:
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise ValueError("Kullanıcı bulunamadı.")
    if target.id == actor.id:
        raise ValueError("Kendi hesabınızı silemezsiniz.")
    admins = db.query(User).filter(User.role == "admin", User.is_active.is_(True)).count()
    if target.role == "admin" and admins <= 1:
        raise ValueError("Son aktif admin silinemez.")
    db.delete(target)
    db.commit()


def reset_user_password(
    db: Session,
    user_id: int,
    new_temporary_password: str,
) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError("Kullanıcı bulunamadı.")
    if len(new_temporary_password) < 4:
        raise ValueError("Geçici şifre en az 4 karakter olmalıdır.")
    user.password_hash = hash_password(new_temporary_password)
    user.must_change_password = True
    user.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return user


def bootstrap_admin(db: Session, username: str, password: str) -> User | None:
    """Create first admin if no users exist."""
    if db.query(User).count() > 0:
        return None
    ok, msg = validate_password(password)
    if not ok:
        raise ValueError(f"İlk admin şifresi geçersiz: {msg}")
    return create_user(
        db,
        username=username,
        password=password,
        role="admin",
        must_change_password=True,
    )
