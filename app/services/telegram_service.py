"""Telegram Bot API — scheduled scan result messages."""

from __future__ import annotations

import logging
import re
from io import BytesIO

import httpx

from app.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from app.services.http_ssl import default_ssl_context

logger = logging.getLogger(__name__)

_TG_API = "https://api.telegram.org"
_MSG_LIMIT = 3900


def telegram_configured() -> bool:
    return bool(TELEGRAM_BOT_TOKEN and parse_chat_ids(TELEGRAM_CHAT_ID))


def parse_chat_ids(raw: str | None) -> list[str]:
    if not raw or not str(raw).strip():
        return []
    parts = re.split(r"[,;\s]+", str(raw).strip())
    return [p for p in parts if p]


def normalize_telegram_storage(raw: str | None) -> str | None:
    ids = parse_chat_ids(raw)
    return ", ".join(ids) if ids else None


def _html_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _api_url(method: str) -> str:
    return f"{_TG_API}/bot{TELEGRAM_BOT_TOKEN}/{method}"


def _raise_if_failed(data: dict, context: str) -> None:
    if data.get("ok"):
        return
    desc = data.get("description") or data.get("error_code") or "Telegram API hatası"
    raise RuntimeError(f"{context}: {desc}")


def _post(method: str, *, json: dict | None = None, data: dict | None = None, files=None) -> dict:
    with httpx.Client(timeout=45, verify=default_ssl_context()) as client:
        res = client.post(_api_url(method), json=json, data=data, files=files)
        try:
            payload = res.json()
        except Exception:
            res.raise_for_status()
            raise RuntimeError(f"Telegram yanıtı okunamadı ({res.status_code})") from None
        _raise_if_failed(payload, f"Telegram {method}")
        return payload


def send_telegram_text(chat_id: str, text: str, *, parse_mode: str = "HTML") -> None:
    _post(
        "sendMessage",
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        },
    )


def send_telegram_document(
    chat_id: str,
    *,
    filename: str,
    content: str,
    caption: str | None = None,
) -> None:
    files = {
        "document": (filename, BytesIO(content.encode("utf-8")), "text/plain"),
    }
    data: dict[str, str] = {"chat_id": str(chat_id)}
    if caption:
        data["caption"] = caption[:1024]
    _post("sendDocument", data=data, files=files)


def send_telegram_scan_result(
    *,
    name: str,
    universe: str,
    timeframe: str,
    match_count: int,
    tv_list_text: str,
    extra_chat_ids: str | None = None,
    filename: str = "tradingview_list.txt",
) -> int:
    """Send summary (+ TV list file when there are matches) to all configured chats."""
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError(
            "Telegram yapılandırılmamış. .env içine TELEGRAM_BOT_TOKEN ve TELEGRAM_CHAT_ID ekleyin."
        )
    chats = list(dict.fromkeys(parse_chat_ids(TELEGRAM_CHAT_ID) + parse_chat_ids(extra_chat_ids)))
    if not chats:
        raise RuntimeError("Telegram chat id yok. TELEGRAM_CHAT_ID veya taramadaki Telegram alanını doldurun.")

    header = (
        f"<b>TradeLABtr tarama</b>\n"
        f"{_html_escape(name)}\n\n"
        f"Evren: {_html_escape(str(universe))}\n"
        f"Zaman dilimi: {_html_escape(str(timeframe))}\n"
        f"Eşleşme: {match_count}"
    )
    symbols = [ln.strip() for ln in (tv_list_text or "").splitlines() if ln.strip() and not ln.startswith("#")]
    if symbols:
        preview = "\n".join(symbols[:40])
        more = f"\n… +{len(symbols) - 40} sembol (dosyada)" if len(symbols) > 40 else ""
        text = f"{header}\n\n<pre>{_html_escape(preview)}{more}</pre>"
    else:
        text = f"{header}\n\nEşleşme yok."
    if len(text) > _MSG_LIMIT:
        text = text[: _MSG_LIMIT - 1] + "…"

    sent = 0
    for chat_id in chats:
        send_telegram_text(chat_id, text)
        if symbols:
            caption = f"{name} — {match_count} eşleşme"
            send_telegram_document(
                chat_id,
                filename=filename,
                content=tv_list_text if tv_list_text.endswith("\n") else f"{tv_list_text}\n",
                caption=caption,
            )
        sent += 1
    logger.info("Telegram scan result sent to %d chat(s)", sent)
    return sent
