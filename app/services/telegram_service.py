"""Telegram Bot API — scheduled scan result messages."""

from __future__ import annotations

import logging
import re
from io import BytesIO

import httpx

from app.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, _normalize_telegram_bot_token
from app.services.http_ssl import default_ssl_context
from app.services.ticker_format import (
    clean_bist_symbol,
    clean_viop_symbol,
    is_bist_universe,
    is_viop_universe,
    to_viop_continuous_symbol,
)

logger = logging.getLogger(__name__)

_TG_API = "https://api.telegram.org"
_MSG_LIMIT = 3900
_VIOP_TP_PCT = 0.04
_VIOP_SL_PCT = 0.03


def _bot_token(override: str | None = None) -> str:
    return _normalize_telegram_bot_token(override or "") or _normalize_telegram_bot_token(
        TELEGRAM_BOT_TOKEN
    )


def telegram_configured() -> bool:
    return bool(_bot_token() and parse_chat_ids(TELEGRAM_CHAT_ID))


def split_telegram_paste(raw: str | None) -> tuple[str | None, str | None]:
    """Split 'TOKEN-5005450345' or a getUpdates URL into (token, chat_id)."""
    if not raw or not str(raw).strip():
        return None, None
    text = (
        str(raw)
        .strip()
        .replace(" ", "")
        .replace("\u2212", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
    )
    url = re.search(r"(?:https?://)?api\.telegram\.org/bot([^/\s]+)", text, re.I)
    if url:
        text = url.group(1)
    if text.lower().startswith("bot") and len(text) > 3 and text[3].isdigit():
        text = text[3:]
    glued = re.fullmatch(r"(\d+:[A-Za-z0-9_-]+?)(-\d{6,})", text)
    if glued:
        return _normalize_telegram_bot_token(glued.group(1)), glued.group(2)
    if re.fullmatch(r"-?\d{6,}", text):
        return None, text
    if ":" in text:
        return _normalize_telegram_bot_token(text), None
    return None, None


def merge_telegram_credentials(
    token: str | None, chat: str | None
) -> tuple[str | None, str | None]:
    t1, c1 = split_telegram_paste(token)
    t2, c2 = split_telegram_paste(chat)
    return t1 or t2, c2 or c1


def parse_chat_ids(raw: str | None) -> list[str]:
    if not raw or not str(raw).strip():
        return []
    _token, glued_chat = split_telegram_paste(raw)
    text = (
        str(raw)
        .strip()
        .replace("\u2212", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
    )
    text = re.sub(r"-\s+", "-", text)
    parts = re.split(r"[,;\s]+", text)
    ids = [p for p in parts if re.fullmatch(r"-?\d+", p)]
    if not ids and glued_chat:
        return [glued_chat]
    return ids


def normalize_telegram_storage(raw: str | None) -> str | None:
    ids = parse_chat_ids(raw)
    return ", ".join(ids) if ids else None


def _html_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _api_url(method: str, token: str | None = None) -> str:
    return f"{_TG_API}/bot{_bot_token(token)}/{method}"


def _raise_if_failed(data: dict, context: str) -> None:
    if data.get("ok"):
        return
    desc = data.get("description") or data.get("error_code") or "Telegram API hatası"
    raise RuntimeError(f"{context}: {desc}")


def _post(
    method: str,
    *,
    json: dict | None = None,
    data: dict | None = None,
    files=None,
    bot_token: str | None = None,
) -> dict:
    with httpx.Client(timeout=45, verify=default_ssl_context()) as client:
        res = client.post(_api_url(method, bot_token), json=json, data=data, files=files)
        try:
            payload = res.json()
        except Exception:
            res.raise_for_status()
            raise RuntimeError(f"Telegram yanıtı okunamadı ({res.status_code})") from None
        _raise_if_failed(payload, f"Telegram {method}")
        return payload


def send_telegram_text(
    chat_id: str, text: str, *, parse_mode: str | None = "HTML", bot_token: str | None = None
) -> None:
    payload: dict[str, object] = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    _post("sendMessage", json=payload, bot_token=bot_token)


def send_telegram_document(
    chat_id: str,
    *,
    filename: str,
    content: str,
    caption: str | None = None,
    bot_token: str | None = None,
) -> None:
    files = {
        "document": (filename, BytesIO(content.encode("utf-8")), "text/plain"),
    }
    data: dict[str, str] = {"chat_id": str(chat_id)}
    if caption:
        data["caption"] = caption[:1024]
    _post("sendDocument", data=data, files=files, bot_token=bot_token)


def _tr_price(value: float) -> str:
    return f"{float(value):.2f}".replace(".", ",")


def _signal_direction(signals: dict | None) -> str:
    sig = signals or {}
    buy = bool(sig.get("bias_ts_buy"))
    sell = bool(sig.get("bias_ts_sell"))
    if buy and sell:
        side = str(sig.get("bias_ts_side") or "buy").strip().lower()
        return "SAT" if side == "sell" else "AL"
    if sell:
        return "SAT"
    return "AL"


def format_signal_telegram_card(
    symbol: str, price: float, direction: str, *, market: str = "viop"
) -> str:
    yon = "SAT" if str(direction).strip().upper() == "SAT" else "AL"
    if yon == "AL":
        tp = price * (1 + _VIOP_TP_PCT)
        sl = price * (1 - _VIOP_SL_PCT)
    else:
        tp = price * (1 - _VIOP_TP_PCT)
        sl = price * (1 + _VIOP_SL_PCT)
    if market == "bist":
        contract = clean_bist_symbol(symbol)
        if contract.startswith("BIST:"):
            contract = contract.split(":", 1)[1]
    else:
        contract = to_viop_continuous_symbol(symbol)
    return (
        f"Kontrat\t: {contract}\n"
        f"Fiyat\t: {_tr_price(price)}\n"
        f"Yön\t\t: {yon}\n"
        f"Kar AL\t: {_tr_price(tp)}\n"
        f"Stop\t\t: {_tr_price(sl)}"
    )


def format_viop_telegram_card(symbol: str, price: float, direction: str) -> str:
    return format_signal_telegram_card(symbol, price, direction, market="viop")


def _signal_cards(results: list[dict] | None, *, market: str) -> list[str]:
    cards: list[str] = []
    for row in results or []:
        try:
            price = float(row.get("price"))
        except (TypeError, ValueError):
            continue
        if price != price or price <= 0:
            continue
        symbol = str(row.get("symbol") or "").strip()
        if not symbol:
            continue
        cards.append(
            format_signal_telegram_card(
                symbol, price, _signal_direction(row.get("signals")), market=market
            )
        )
    return cards


def _is_viop_scan(
    universe: str,
    custom_source_universe: str | None,
    results: list[dict] | None = None,
) -> bool:
    if is_viop_universe(universe) or is_viop_universe(custom_source_universe or ""):
        return True
    if is_bist_universe(universe) or is_bist_universe(custom_source_universe or ""):
        return False
    return any(
        clean_viop_symbol(str(row.get("symbol") or "")).startswith("F_")
        for row in (results or [])
    )


def _is_bist_scan(universe: str, custom_source_universe: str | None) -> bool:
    return is_bist_universe(universe) or is_bist_universe(custom_source_universe or "")


def _resolve_chats(extra_chat_ids: str | None, bot_token: str | None = None) -> list[str]:
    if not _bot_token(bot_token):
        raise RuntimeError(
            "Telegram yapılandırılmamış. .env veya taramaya TELEGRAM_BOT_TOKEN ekleyin."
        )
    override = parse_chat_ids(extra_chat_ids)
    chats = override or parse_chat_ids(TELEGRAM_CHAT_ID)
    if not chats:
        raise RuntimeError(
            "Telegram chat id yok. Taramadaki Telegram alanını veya .env TELEGRAM_CHAT_ID değerini doldurun."
        )
    return chats


def send_telegram_scan_result(
    *,
    name: str,
    universe: str,
    timeframe: str,
    match_count: int,
    tv_list_text: str,
    extra_chat_ids: str | None = None,
    filename: str = "tradingview_list.txt",
    results: list[dict] | None = None,
    custom_source_universe: str | None = None,
    bot_token: str | None = None,
) -> int:
    """Send scan results. VIOP/BIST: one card per match, no file, skip if empty."""
    bot_token, extra_chat_ids = merge_telegram_credentials(bot_token, extra_chat_ids)
    chats = _resolve_chats(extra_chat_ids, bot_token)
    card_market = None
    if _is_viop_scan(universe, custom_source_universe, results):
        card_market = "viop"
    elif _is_bist_scan(universe, custom_source_universe):
        card_market = "bist"
    if card_market:
        cards = _signal_cards(results, market=card_market)
        if not cards:
            logger.info("%s Telegram skipped: no matches", card_market.upper())
            return 0
        sent = 0
        for chat_id in chats:
            for card in cards:
                send_telegram_text(chat_id, card, parse_mode=None, bot_token=bot_token)
                sent += 1
        logger.info(
            "%s Telegram sent %d card(s) to %d chat(s)",
            card_market.upper(),
            len(cards),
            len(chats),
        )
        return sent

    if match_count <= 0 and not (results or []):
        logger.info("Telegram skipped: no matches")
        return 0

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
        send_telegram_text(chat_id, text, bot_token=bot_token)
        if symbols:
            caption = f"{name} — {match_count} eşleşme"
            send_telegram_document(
                chat_id,
                filename=filename,
                content=tv_list_text if tv_list_text.endswith("\n") else f"{tv_list_text}\n",
                caption=caption,
                bot_token=bot_token,
            )
        sent += 1
    logger.info("Telegram scan result sent to %d chat(s)", sent)
    return sent
