from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, create_engine, text
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


class ScheduledScan(Base):
    __tablename__ = "scheduled_scans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    config_json = Column(Text, nullable=False)
    schedule_type = Column(String(32), nullable=False, default="daily")  # hourly, every_4h, daily, weekly
    hour = Column(Integer, nullable=False, default=8)
    minute = Column(Integer, nullable=False, default=30)
    end_hour = Column(Integer, nullable=True)  # hourly/every_4h window end (inclusive)
    weekday = Column(Integer, nullable=True)  # legacy weekly (0=Mon .. 6=Sun)
    weekdays = Column(Text, nullable=True)  # comma-separated 0..6 for daily multi-day
    timezone = Column(String(64), nullable=False, default="Europe/Istanbul")
    email_to = Column(Text, nullable=False)
    telegram_to = Column(Text, nullable=True)
    notify_telegram = Column(Boolean, nullable=False, default=True)
    enabled = Column(Boolean, nullable=False, default=True)
    last_run_at = Column(DateTime, nullable=True)
    last_status = Column(String(32), nullable=True)
    last_match_count = Column(Integer, nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ScanRun(Base):
    __tablename__ = "scan_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scheduled_scan_id = Column(Integer, nullable=False, index=True)
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    finished_at = Column(DateTime, nullable=True)
    status = Column(String(32), nullable=False, default="running")
    match_count = Column(Integer, nullable=True)
    results_json = Column(Text, nullable=True)
    tv_list_text = Column(Text, nullable=True)
    email_sent = Column(Boolean, nullable=False, default=False)
    error_message = Column(Text, nullable=True)


class TrackUserSettings(Base):
    __tablename__ = "track_user_settings"

    user_id = Column(Integer, primary_key=True)
    target_pct = Column(Float, nullable=False, default=8.0)
    stop_pct = Column(Float, nullable=False, default=5.0)
    auto_track_enabled = Column(Boolean, nullable=False, default=True)
    auto_close_on_tp_sl = Column(Boolean, nullable=False, default=True)
    auto_close_weekend_intraday = Column(Boolean, nullable=False, default=False)
    weekend_close_hour = Column(Integer, nullable=False, default=23)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class TrackPosition(Base):
    __tablename__ = "track_positions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    symbol = Column(String(32), nullable=False, index=True)
    universe = Column(String(32), nullable=False)
    entry_price = Column(Float, nullable=False)
    entry_at = Column(DateTime, nullable=False)
    target_price = Column(Float, nullable=False)
    stop_price = Column(Float, nullable=False)
    target_pct = Column(Float, nullable=False)
    stop_pct = Column(Float, nullable=False)
    current_price = Column(Float, nullable=True)
    last_checked_at = Column(DateTime, nullable=True)
    status = Column(String(32), nullable=False, default="active", index=True)
    source_type = Column(String(32), nullable=False, default="scheduled")
    scheduled_scan_id = Column(Integer, nullable=True, index=True)
    scan_run_id = Column(Integer, nullable=True, index=True)
    source_label = Column(String(255), nullable=False, default="")
    schedule_type = Column(String(32), nullable=True)
    timeframe = Column(String(16), nullable=False, default="1d")
    exit_price = Column(Float, nullable=True)
    exit_at = Column(DateTime, nullable=True)
    exit_reason = Column(String(64), nullable=True)
    benchmark_symbol = Column(String(32), nullable=True)
    benchmark_entry_price = Column(Float, nullable=True)
    benchmark_current_price = Column(Float, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class TrackBenchmarkLog(Base):
    __tablename__ = "track_benchmark_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    universe = Column(String(32), nullable=False, index=True)
    price = Column(Float, nullable=False)
    recorded_at = Column(DateTime, nullable=False)


class TrackPriceLog(Base):
    __tablename__ = "track_price_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    position_id = Column(Integer, nullable=False, index=True)
    price = Column(Float, nullable=False)
    recorded_at = Column(DateTime, nullable=False)


def _migrate_db() -> None:
    """Schema updates for existing SQLite DBs. create_all first for fresh installs."""
    Base.metadata.create_all(engine)

    with engine.connect() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(pine_scripts)"))}
        if cols and "pine_content" not in cols:
            conn.execute(text("ALTER TABLE pine_scripts ADD COLUMN pine_content TEXT"))
        if cols and "input_defaults" not in cols:
            conn.execute(text("ALTER TABLE pine_scripts ADD COLUMN input_defaults TEXT"))

        sched_cols = {
            row[1] for row in conn.execute(text("PRAGMA table_info(scheduled_scans)"))
        }
        if sched_cols and "weekdays" not in sched_cols:
            conn.execute(text("ALTER TABLE scheduled_scans ADD COLUMN weekdays TEXT"))
        if sched_cols and "telegram_to" not in sched_cols:
            conn.execute(text("ALTER TABLE scheduled_scans ADD COLUMN telegram_to TEXT"))
        if sched_cols and "notify_telegram" not in sched_cols:
            conn.execute(
                text(
                    "ALTER TABLE scheduled_scans ADD COLUMN notify_telegram BOOLEAN "
                    "NOT NULL DEFAULT 1"
                )
            )
        if sched_cols and "end_hour" not in sched_cols:
            conn.execute(text("ALTER TABLE scheduled_scans ADD COLUMN end_hour INTEGER"))
            conn.execute(
                text(
                    "UPDATE scheduled_scans SET end_hour = 18 "
                    "WHERE schedule_type IN ('hourly', 'every_4h') AND end_hour IS NULL"
                )
            )
            conn.execute(
                text(
                    "UPDATE scheduled_scans SET hour = 10 "
                    "WHERE schedule_type IN ('hourly', 'every_4h') AND hour = 8"
                )
            )

        pos_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(track_positions)"))}
        if pos_cols:
            if "benchmark_symbol" not in pos_cols:
                conn.execute(text("ALTER TABLE track_positions ADD COLUMN benchmark_symbol TEXT"))
            if "benchmark_entry_price" not in pos_cols:
                conn.execute(text("ALTER TABLE track_positions ADD COLUMN benchmark_entry_price REAL"))
            if "benchmark_current_price" not in pos_cols:
                conn.execute(text("ALTER TABLE track_positions ADD COLUMN benchmark_current_price REAL"))
        conn.commit()


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
