"""VIOP pay alarms: same Pine, per-alarm params and contract set."""

from __future__ import annotations

import json
from typing import Any

from app.services.ticker_format import to_viop_continuous_symbol
from app.services.viop_contracts import SEED_PATH, _load_json

ALARM_KIND = "viop_pay"
ALARM_TIMEFRAMES = ("3m", "5m", "15m", "30m", "1h")


def list_viop_pay_contracts() -> list[dict[str, str]]:
    data = _load_json(SEED_PATH) or {}
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in data.get("contracts") or []:
        if str(row.get("group") or "") != "pay":
            continue
        ticker = str(row.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        contract = to_viop_continuous_symbol(ticker)
        if contract in seen:
            continue
        seen.add(contract)
        out.append(
            {
                "ticker": ticker,
                "contract": contract,
                "name": str(row.get("name") or ticker),
            }
        )
    out.sort(key=lambda r: r["ticker"])
    return out


def known_pay_contracts() -> set[str]:
    return {r["contract"] for r in list_viop_pay_contracts()}


def is_alarm_config(cfg: dict[str, Any] | None) -> bool:
    return bool(cfg and cfg.get("alarm"))


def config_from_row(row) -> dict[str, Any]:
    try:
        return json.loads(row.config_json or "{}")
    except json.JSONDecodeError:
        return {}


def parse_contracts(raw: str | list[str] | None) -> list[str]:
    if isinstance(raw, list):
        parts = raw
    else:
        text = str(raw or "").replace(";", ",").replace("\n", ",")
        parts = text.split(",")
    known = known_pay_contracts()
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        contract = to_viop_continuous_symbol(part)
        if not contract or contract in seen:
            continue
        if known and contract not in known:
            continue
        seen.add(contract)
        out.append(contract)
    return out


def build_scan_config(
    *,
    pine_script_id: int,
    pine_input_overrides: dict[str, Any] | None,
    contracts: list[str],
    timeframe: str,
    telegram_to: str | None = None,
    telegram_bot_token: str | None = None,
) -> dict[str, Any]:
    tf = (timeframe or "15m").strip().lower()
    if tf not in ALARM_TIMEFRAMES:
        tf = "15m"
    symbols = parse_contracts(contracts)
    return {
        "alarm": True,
        "alarm_kind": ALARM_KIND,
        "universe": "custom",
        "custom_source_universe": "viop",
        "custom_symbols": ",".join(symbols),
        "timeframe": tf,
        "filters": [],
        "pine_script_id": int(pine_script_id),
        "require_pine_al": True,
        "pine_input_overrides": dict(pine_input_overrides or {}),
        "max_symbols": max(len(symbols), 1),
        "notify_telegram": True,
        "telegram_to": telegram_to,
        "telegram_bot_token": telegram_bot_token,
    }


def alarm_view(row_dict: dict[str, Any]) -> dict[str, Any]:
    cfg = row_dict.get("scan_config") or {}
    contracts = parse_contracts(cfg.get("custom_symbols") or "")
    return {
        "id": row_dict.get("id"),
        "name": row_dict.get("name"),
        "enabled": bool(row_dict.get("enabled")),
        "pine_script_id": cfg.get("pine_script_id"),
        "pine_input_overrides": cfg.get("pine_input_overrides") or {},
        "contracts": contracts,
        "timeframe": cfg.get("timeframe") or row_dict.get("schedule_type") or "15m",
        "hour": row_dict.get("hour"),
        "minute": row_dict.get("minute"),
        "end_hour": row_dict.get("end_hour"),
        "weekdays": row_dict.get("weekdays") or [0, 1, 2, 3, 4],
        "timezone": row_dict.get("timezone") or "Europe/Istanbul",
        "telegram_to": row_dict.get("telegram_to"),
        "notify_telegram": bool(row_dict.get("notify_telegram", True)),
        "last_run_istanbul": row_dict.get("last_run_istanbul"),
        "next_run_istanbul": row_dict.get("next_run_istanbul"),
        "last_status": row_dict.get("last_status"),
        "last_match_count": row_dict.get("last_match_count"),
        "last_error": row_dict.get("last_error"),
        "created_at": row_dict.get("created_at"),
    }
