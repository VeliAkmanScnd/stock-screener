"""Help topics: markdown docs and downloads."""

from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.api.auth_deps import get_current_user
from app.config import BASE_DIR
from app.database import User

router = APIRouter(prefix="/api/help", tags=["help"])

HELP_DIR = BASE_DIR / "docs" / "help"

TOPICS: list[dict[str, str]] = [
    {"id": "genel", "title": "Genel bakış", "file": "genel.md", "summary": "Sekmeler, günlük akış ve örnek senaryo."},
    {"id": "ozet", "title": "Özet (günlük pano)", "file": "ozet.md", "summary": "Bugünkü taramalar, eşleşmeler ve tekrarlar."},
    {"id": "tarama", "title": "Tarama", "file": "tarama.md", "summary": "Evren, filtre, Pine ve sonuçlar."},
    {"id": "performans", "title": "Performans takibi", "file": "performans.md", "summary": "Pozisyonlar, TP/SL, R sıralaması ve örnekler."},
    {"id": "zamanlanmis", "title": "Zamanlanmış taramalar", "file": "zamanlanmis.md", "summary": "Kayıt, saat ve kuyruk."},
    {"id": "telegram", "title": "Telegram ve e-posta", "file": "telegram.md", "summary": "Kart formatı, bot ve grup."},
    {"id": "evrenler", "title": "Evrenler ve veri", "file": "evrenler.md", "summary": "ABD, BIST, VIOP, Binance."},
    {"id": "kullanicilar", "title": "Kullanıcılar ve giriş", "file": "kullanicilar.md", "summary": "Admin, şifre, PC / VPS."},
]


def _topic(topic_id: str) -> dict[str, str] | None:
    if topic_id == "izleme":
        topic_id = "performans"
    return next((t for t in TOPICS if t["id"] == topic_id), None)


def _read_markdown(topic: dict[str, str]) -> str:
    path = HELP_DIR / topic["file"]
    if not path.is_file():
        raise HTTPException(404, "Döküman bulunamadı")
    return path.read_text(encoding="utf-8")


@router.get("/topics")
def list_topics(_user: User = Depends(get_current_user)):
    return {"topics": [{"id": t["id"], "title": t["title"], "summary": t["summary"]} for t in TOPICS]}


@router.get("/topics/{topic_id}")
def get_topic(topic_id: str, _user: User = Depends(get_current_user)):
    topic = _topic(topic_id)
    if not topic:
        raise HTTPException(404, "Başlık bulunamadı")
    return {
        "id": topic["id"],
        "title": topic["title"],
        "summary": topic["summary"],
        "markdown": _read_markdown(topic),
        "download_url": f"/api/help/topics/{topic['id']}/download",
    }


@router.get("/topics/{topic_id}/download")
def download_topic(topic_id: str, _user: User = Depends(get_current_user)):
    topic = _topic(topic_id)
    if not topic:
        raise HTTPException(404, "Başlık bulunamadı")
    body = _read_markdown(topic).encode("utf-8")
    filename = f"tradelabtr-{topic['id']}.md"
    return Response(
        content=body,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/download.zip")
def download_all(_user: User = Depends(get_current_user)):
    buf = BytesIO()
    with ZipFile(buf, "w", ZIP_DEFLATED) as zf:
        for topic in TOPICS:
            path = HELP_DIR / topic["file"]
            if path.is_file():
                zf.writestr(f"tradelabtr-{topic['id']}.md", path.read_text(encoding="utf-8"))
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="tradelabtr-yardim.zip"'},
    )
