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
    host = os.getenv("HOST", "0.0.0.0").strip() or "0.0.0.0"
    port = int(os.getenv("PORT", "8000"))

    print(f"TradeLABtr bind: http://{host}:{port}", flush=True)
    print(f"Tarayici (bu makine): http://127.0.0.1:{port}/login", flush=True)
    if host in {"127.0.0.1", "localhost"}:
        print(
            "Uyari: HOST=127.0.0.1 yalnizca bu makineden acilir. "
            "VPS icin start-tradelab.bat kullanin (HOST=0.0.0.0 zorlar) "
            "veya .env icine HOST=0.0.0.0 yazin.",
            flush=True,
        )
    else:
        print(
            "Baska PC'den: http://<VPS-IPv4>:{}/login  "
            "(Windows Firewall'da TCP {} acik olmali)".format(port, port),
            flush=True,
        )
    print("http://localhost kullanmayin — Windows IPv6'ya dusebilir.", flush=True)
    print(f"Log: {log_path}", flush=True)

    import uvicorn

    try:
        uvicorn.run("app.main:app", host=host, port=port, reload=reload)
    except OSError as exc:
        print(f"[HATA] Port {port} dinlenemedi: {exc}", flush=True)
        print(
            "Baska bir TradeLABtr penceresi aciksa onu kapatin, "
            "sonra start-tradelab.bat ile yeniden baslatin.",
            flush=True,
        )
        raise
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        if code not in (0, None):
            _pause_on_windows()
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
