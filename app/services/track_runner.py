"""Scheduled price checks for track positions."""

from __future__ import annotations

import logging

from app.database import SessionLocal
from app.services.track_service import maybe_weekend_expire, update_active_prices

logger = logging.getLogger(__name__)


def run_track_price_update() -> None:
    db = SessionLocal()
    try:
        stats = update_active_prices(db)
        logger.info(
            "Track price update: checked=%s closed=%s",
            stats["checked"],
            stats["closed"],
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
