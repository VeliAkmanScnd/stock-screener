import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
STORAGE_DIR = BASE_DIR / "storage"
PINE_DIR = STORAGE_DIR / "pine_scripts"
DB_PATH = STORAGE_DIR / "screener.db"

DEFAULT_TIMEFRAME = "1d"
DEFAULT_LOOKBACK_DAYS = 400
MAX_SYMBOLS_PER_SCAN = 20000
SCAN_BATCH_SIZE = 25

# Common EMA presets for UI
EMA_PRESETS = [9, 12, 20, 21, 26, 50, 100, 200]

# Twelve Data — BIST OHLCV (free key: https://twelvedata.com/apikey)
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "").strip()
TWELVE_DATA_BASE_URL = "https://api.twelvedata.com"

# Auth — first admin created on empty DB (change password after deploy)
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin").strip().lower()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Admin!12345")
SESSION_SECRET = os.getenv("SESSION_SECRET", secrets.token_hex(32))
ADMIN_MUST_CHANGE_ON_NEXT_LOGIN = os.getenv(
    "ADMIN_MUST_CHANGE_ON_NEXT_LOGIN", ""
).strip().lower() in ("1", "true", "yes")
SESSION_COOKIE = "screener_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 7  # 7 days
