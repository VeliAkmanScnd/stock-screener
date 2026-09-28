"""Start the stock screener web app."""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def _pause_on_windows() -> None:
    if os.name == "nt" and sys.stdin.isatty():
        try:
            input("Enter'a basarak kapat...")
        except EOFError:
            pass


def main() -> int:
    (ROOT / "storage").mkdir(parents=True, exist_ok=True)
    log_path = ROOT / "storage" / "server.log"

    import logging

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

    reload = os.getenv("RUN_RELOAD", "").lower() in ("1", "true", "yes")
    host = os.getenv("HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = int(os.getenv("PORT", "8000"))

    print(f"TradeLABtr dinleniyor: http://{host}:{port}", flush=True)
    if host in {"127.0.0.1", "localhost"}:
        print(
            "Uyari: HOST=127.0.0.1 yalnizca bu makineden acilir. "
            "VPS icin .env icine HOST=0.0.0.0 yazin (veya start-tradelab.bat kullanin).",
            flush=True,
        )
    print(f"Log: {log_path}", flush=True)

    import uvicorn

    uvicorn.run("app.main:app", host=host, port=port, reload=reload)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        try:
            (ROOT / "storage").mkdir(parents=True, exist_ok=True)
            with (ROOT / "storage" / "server.log").open("a", encoding="utf-8") as fh:
                fh.write("\n--- crash ---\n")
                traceback.print_exc(file=fh)
        except OSError:
            pass
        _pause_on_windows()
        raise SystemExit(1)
