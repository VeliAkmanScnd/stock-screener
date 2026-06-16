"""Read/write saved Pine scripts (DB + optional file)."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import PINE_DIR
from app.database import PineScript


def _safe_slug(name: str) -> str:
    slug = re.sub(r"[^\w\-]+", "_", name.strip())
    return slug.strip("_") or "script"


def save_pine_script(
    db: Session,
    *,
    content: str,
    display_name: str,
    original_filename: str,
    al_condition: str | None,
    al_source: str | None,
) -> PineScript:
    PINE_DIR.mkdir(parents=True, exist_ok=True)
    slug = _safe_slug(display_name)

    row = PineScript(
        name=display_name,
        filename=original_filename,
        file_path="",
        pine_content=content,
        al_condition=al_condition,
        al_source=al_source,
    )
    db.add(row)
    db.flush()

    dest = PINE_DIR / f"{row.id}_{slug}.txt"
    dest.write_text(content, encoding="utf-8")
    row.file_path = str(dest.resolve())
    db.commit()
    db.refresh(row)
    return row


def load_pine_content(row: PineScript) -> str:
    if row.pine_content and row.pine_content.strip():
        return row.pine_content

    path = Path(row.file_path) if row.file_path else None
    if path and path.is_file():
        text = path.read_text(encoding="utf-8", errors="replace")
        return text

    raise HTTPException(
        400,
        f'"{row.name}" script dosyası diskte yok. Lütfen Pine dosyasını yeniden yükleyin veya kaydı silin.',
    )
