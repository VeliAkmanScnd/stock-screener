"""Node sidecar for VIOP/Hisse ranking (/api/screener)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

from app.config import BASE_DIR

CALC_DIR = BASE_DIR / "calc"
CALC_OUT = CALC_DIR / "out"
CALC_API_HOST = os.getenv("CALC_API_HOST", "127.0.0.1").strip() or "127.0.0.1"
CALC_API_PORT = int(os.getenv("CALC_API_PORT", "4318"))

_proc: subprocess.Popen | None = None


def calc_api_base() -> str:
    return f"http://{CALC_API_HOST}:{CALC_API_PORT}"


def calc_ui_available() -> bool:
    return (CALC_OUT / "index.html").is_file()


def start_calc_api() -> None:
    global _proc
    if _proc is not None and _proc.poll() is None:
        return
    node = shutil.which("node")
    script = CALC_DIR / "api-server.mjs"
    if node is None or not script.is_file():
        print(
            "Calc API: node veya calc/api-server.mjs yok; VIOP/Hisse lot hesabı çalışır, sıralama kapalı.",
            file=sys.stderr,
        )
        return
    env = os.environ.copy()
    env["CALC_API_HOST"] = CALC_API_HOST
    env["CALC_API_PORT"] = str(CALC_API_PORT)
    env["PORT"] = str(CALC_API_PORT)
    _proc = subprocess.Popen(
        [node, str(script)],
        cwd=str(CALC_DIR),
        env=env,
    )
    print(f"Calc API başlatıldı (pid {_proc.pid}) {calc_api_base()}", file=sys.stderr)


def stop_calc_api() -> None:
    global _proc
    if _proc is None:
        return
    if _proc.poll() is None:
        _proc.terminate()
        try:
            _proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            _proc.kill()
            _proc.wait(timeout=3)
    _proc = None
