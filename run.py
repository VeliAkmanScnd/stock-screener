"""Start the stock screener web app."""

import os
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

if __name__ == "__main__":
    # reload=False keeps APScheduler jobs stable (scheduled scans only run while server is up).
    reload = os.getenv("RUN_RELOAD", "").lower() in ("1", "true", "yes")
    # Local default 127.0.0.1; on VPS set HOST=0.0.0.0 in .env.
    host = os.getenv("HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app.main:app", host=host, port=port, reload=reload)
