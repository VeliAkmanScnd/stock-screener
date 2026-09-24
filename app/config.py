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

# Twelve Data — optional BIST fallback / intraday (https://twelvedata.com/apikey)
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "").strip()
TWELVE_DATA_BASE_URL = "https://api.twelvedata.com"

# BIST OHLCV: yfinance | borsapy | twelvedata | auto
BIST_DATA_PROVIDER = os.getenv("BIST_DATA_PROVIDER", "yfinance").strip().lower()
BIST_CACHE_TTL_SECONDS = int(os.getenv("BIST_CACHE_TTL_SECONDS", "900"))
BIST_TD_FALLBACK = os.getenv("BIST_TD_FALLBACK", "false").strip().lower() in (
    "1",
    "true",
    "yes",
)

# borsapy + TradingView live BIST (optional — see .env.example)
TRADINGVIEW_SESSION_ID = os.getenv("TRADINGVIEW_SESSION_ID", "").strip()
TRADINGVIEW_SESSION_SIGN = os.getenv("TRADINGVIEW_SESSION_SIGN", "").strip()

# Auth — first admin created on empty DB (change password after deploy)
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin").strip().lower()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Admin!12345")
SESSION_SECRET = os.getenv("SESSION_SECRET", secrets.token_hex(32))
ADMIN_MUST_CHANGE_ON_NEXT_LOGIN = os.getenv(
    "ADMIN_MUST_CHANGE_ON_NEXT_LOGIN", ""
).strip().lower() in ("1", "true", "yes")
SESSION_COOKIE = "screener_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 7  # 7 days

# Scheduled scans
DEFAULT_SCHEDULE_TIMEZONE = os.getenv("DEFAULT_SCHEDULE_TIMEZONE", "Europe/Istanbul").strip()

# SMTP — optional; required for scheduled scan emails
SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
SMTP_FROM = os.getenv("SMTP_FROM", "").strip()
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").strip().lower() in ("1", "true", "yes")

# Telegram — optional; scheduled scan results (in addition to email)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# Performance tracking (TP/SL watchlist)
TRACK_DEFAULT_TARGET_PCT = float(os.getenv("TRACK_DEFAULT_TARGET_PCT", "8"))
TRACK_DEFAULT_STOP_PCT = float(os.getenv("TRACK_DEFAULT_STOP_PCT", "5"))
TRACK_PRICE_CHECK_TIMEZONE = os.getenv("TRACK_PRICE_CHECK_TIMEZONE", DEFAULT_SCHEDULE_TIMEZONE).strip()
