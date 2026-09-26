"""Scheduled price checks for track positions."""

from __future__ import annotations

import logging

from app.database import SessionLocal
from app.services.track_service import (
    archive_expired_watches,
    maybe_weekend_expire,
    update_active_prices,
)

logger = logging.getLogger(__name__)


def run_track_price_update() -> None:
    db = SessionLocal()
    try:
        stats = update_active_prices(db)
        logger.info(
            "Track price update: checked=%s closed=%s hit_tp=%s archived=%s",
            stats.get("checked"),
            stats.get("closed"),
            stats.get("hit_tp"),
            stats.get("archived"),
        )
    except Exception:
        logger.exception("Track price update failed")
    finally:
        db.close()


def run_track_weekend_expire() -> None:
    db = SessionLocal()
    try:
        expired = maybe_weekend_expire(db)
        if expired:
            logger.info("Track weekend expire: %s positions", expired)
    except Exception:
        logger.exception("Track weekend expire failed")
    finally:
        db.close()


def run_track_archive() -> None:
    db = SessionLocal()
    try:
        archived = archive_expired_watches(db)
        if archived:
            logger.info("Track archive: %s positions", archived)
    except Exception:
        logger.exception("Track archive failed")
    finally:
        db.close()
