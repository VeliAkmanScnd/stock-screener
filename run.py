"""Start the stock screener web app."""

import os

import uvicorn

if __name__ == "__main__":
    # reload=False keeps APScheduler jobs stable (scheduled scans only run while server is up).
    reload = os.getenv("RUN_RELOAD", "").lower() in ("1", "true", "yes")
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=reload)
