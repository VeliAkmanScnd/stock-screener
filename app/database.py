from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import DB_PATH, PINE_DIR, STORAGE_DIR


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(16), nullable=False, default="user")  # admin | user
    must_change_password = Column(Boolean, nullable=False, default=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class PineScript(Base):
    __tablename__ = "pine_scripts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=False, default="")
    pine_content = Column(Text, nullable=True)
    al_condition = Column(Text, nullable=True)
    al_source = Column(String(64), nullable=True)  # plotshape, variable, alertcondition
    input_defaults = Column(Text, nullable=True)  # JSON: saved Pine input overrides
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


def _migrate_db() -> None:
    """Schema updates for existing SQLite DBs."""
    with engine.connect() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(pine_scripts)"))}
        if "pine_content" not in cols:
            conn.execute(text("ALTER TABLE pine_scripts ADD COLUMN pine_content TEXT"))
        if "input_defaults" not in cols:
            conn.execute(text("ALTER TABLE pine_scripts ADD COLUMN input_defaults TEXT"))
        conn.commit()

    Base.metadata.create_all(engine)


STORAGE_DIR.mkdir(parents=True, exist_ok=True)
PINE_DIR.mkdir(parents=True, exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
_migrate_db()


def bootstrap_auth() -> None:
    from app.config import (
        ADMIN_MUST_CHANGE_ON_NEXT_LOGIN,
        ADMIN_PASSWORD,
        ADMIN_USERNAME,
    )
    from app.services.auth_service import bootstrap_admin

    db = SessionLocal()
    try:
        bootstrap_admin(db, ADMIN_USERNAME, ADMIN_PASSWORD)
        if ADMIN_MUST_CHANGE_ON_NEXT_LOGIN:
            admin = (
                db.query(User)
                .filter(User.username == ADMIN_USERNAME, User.role == "admin")
                .first()
            )
            if admin:
                admin.must_change_password = True
                db.commit()
    finally:
        db.close()


bootstrap_auth()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
