"""Ensure only one app process runs APScheduler (avoids duplicate scans/emails)."""

from __future__ import annotations

import atexit
import logging
import os
import sys

from app.config import STORAGE_DIR

logger = logging.getLogger(__name__)

_LOCK_PATH = STORAGE_DIR / "scheduler.lock"
_lock_handle = None


def acquire_scheduler_lock() -> bool:
    """Return True if this process should own the scan scheduler."""
    global _lock_handle
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    handle = open(_LOCK_PATH, "a+b")
    if handle.tell() < 1:
        handle.write(b"0")
        handle.flush()

    try:
        if sys.platform == "win32":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        logger.warning(
            "Another server process already runs scheduled scans. "
            "Close the other terminal / stop the other python.exe on port 8000, then restart."
        )
        return False

    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()).encode())
    handle.flush()
    _lock_handle = handle
    atexit.register(release_scheduler_lock)
    logger.info("Scheduler lock acquired (pid %s)", os.getpid())
    return True


def release_scheduler_lock() -> None:
    global _lock_handle
    if _lock_handle is None:
        return
    try:
        if sys.platform == "win32":
            import msvcrt

            _lock_handle.seek(0)
            msvcrt.locking(_lock_handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(_lock_handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        _lock_handle.close()
    except OSError:
        pass
    _lock_handle = None
