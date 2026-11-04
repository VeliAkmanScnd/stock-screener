"""VIOP pay alarms: same Pine, per-alarm params and contract set."""

from __future__ import annotations

import json
import zipfile
from io import BytesIO
from typing import Any
from xml.sax.saxutils import escape

from app.services.ticker_format import to_viop_continuous_symbol
from app.services.viop_contracts import SEED_PATH, _load_json

ALARM_KIND = "viop_pay"
ALARM_TIMEFRAMES = ("3m", "5m", "15m", "30m", "1h")
_WEEKDAY_LABELS = ("Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz")
# Column order matches the desk export template (kontratlar before period;
# "% kazanç" is manual — not stored in DB, exported blank).
_ALARM_EXPORT_BASE = (
    ("id", "id"),
    ("name", "ad"),
    ("enabled", "aktif"),
    ("pine_script_id", "pine_id"),
    ("pine_name", "pine"),
    ("contracts", "kontratlar"),
    ("pct_gain", "% kazanç"),
    ("timeframe", "periyot"),
    ("hour", "baslangic_saat"),
    ("minute", "dakika"),
    ("end_hour", "bitis_saat"),
    ("weekdays", "gunler"),
    ("timezone", "saat_dilimi"),
    ("contract_count", "kontrat_sayisi"),
    ("notify_telegram", "telegram"),
    ("telegram_to", "telegram_chat"),
    ("last_run_istanbul", "son_calisma"),
    ("next_run_istanbul", "sonraki"),
    ("last_status", "son_durum"),
    ("last_match_count", "son_eslesen"),
    ("last_error", "son_hata"),
    ("created_at", "olusturma"),
)
_ALARM_EXPORT_PARAM_ORDER = (
    "allow_long",
    "allow_short",
    "exitMode",
    "ha_htf",
    "ha_len",
    "ha_len2",
    "osc_len",
    "rrMult",
    "swingBars",
    "scan_side",
    "reverse_exit",
    "require_bar",
    "sl_pct",
    "maxSame",
    "tp_pct",
)


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


def _weekdays_label(days: list[Any] | None) -> str:
    labels = []
    for d in days or []:
        try:
            i = int(d)
        except (TypeError, ValueError):
            continue
        if 0 <= i < len(_WEEKDAY_LABELS):
            labels.append(_WEEKDAY_LABELS[i])
    return ",".join(labels)


def _excel_cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "evet" if value else "hayir"
    if isinstance(value, (list, tuple)):
        return ",".join(str(v) for v in value)
    return str(value)


def _xml_text(value: Any) -> str:
    return escape(_excel_cell_text(value), {"'": "&apos;", '"': "&quot;"})


def _alarm_export_param_keys(alarms: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    extras: list[str] = []
    for row in alarms:
        ov = row.get("pine_input_overrides") or {}
        if not isinstance(ov, dict):
            continue
        for key in ov:
            name = str(key)
            if name in seen:
                continue
            seen.add(name)
            extras.append(name)
    ordered = [k for k in _ALARM_EXPORT_PARAM_ORDER if k in seen]
    tail = sorted(k for k in extras if k not in _ALARM_EXPORT_PARAM_ORDER)
    return ordered + tail


def alarm_export_table(
    alarms: list[dict[str, Any]],
    pine_names: dict[int, str] | None = None,
) -> tuple[list[str], list[list[Any]]]:
    """Flatten alarm settings + Pine overrides into Excel columns."""
    names = pine_names or {}
    param_keys = _alarm_export_param_keys(alarms)
    headers = [title for _, title in _ALARM_EXPORT_BASE] + [f"param_{k}" for k in param_keys]
    body: list[list[Any]] = []
    for row in alarms:
        pine_id = row.get("pine_script_id")
        try:
            pine_key = int(pine_id) if pine_id is not None else None
        except (TypeError, ValueError):
            pine_key = None
        contracts = row.get("contracts") or []
        base = {
            "id": row.get("id"),
            "name": row.get("name"),
            "enabled": bool(row.get("enabled")),
            "pine_script_id": pine_id,
            "pine_name": names.get(pine_key, "") if pine_key is not None else "",
            "contracts": ",".join(str(c) for c in contracts),
            "pct_gain": row.get("pct_gain", ""),
            "timeframe": row.get("timeframe"),
            "hour": row.get("hour"),
            "minute": row.get("minute"),
            "end_hour": row.get("end_hour"),
            "weekdays": _weekdays_label(row.get("weekdays")),
            "timezone": row.get("timezone"),
            "contract_count": len(contracts),
            "notify_telegram": bool(row.get("notify_telegram", True)),
            "telegram_to": row.get("telegram_to") or "",
            "last_run_istanbul": row.get("last_run_istanbul") or "",
            "next_run_istanbul": row.get("next_run_istanbul") or "",
            "last_status": row.get("last_status") or "",
            "last_match_count": row.get("last_match_count"),
            "last_error": row.get("last_error") or "",
            "created_at": row.get("created_at") or "",
        }
        ov = row.get("pine_input_overrides") if isinstance(row.get("pine_input_overrides"), dict) else {}
        values = [base[key] for key, _ in _ALARM_EXPORT_BASE]
        values.extend(ov.get(k, "") for k in param_keys)
        body.append(values)
    return headers, body


def build_alarms_xlsx(headers: list[str], rows: list[list[Any]]) -> bytes:
    """Minimal Office Open XML workbook (opens in Excel)."""

    def cell_xml(col_i: int, row_i: int, value: Any) -> str:
        ref = f"{_xlsx_col(col_i)}{row_i}"
        text = _xml_text(value)
        if text == "":
            return f'<c r="{ref}"/>'
        return f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>'

    sheet_rows = []
    for r_i, values in enumerate([headers, *rows], start=1):
        cells = "".join(cell_xml(c_i, r_i, val) for c_i, val in enumerate(values, start=1))
        sheet_rows.append(f'<row r="{r_i}">{cells}</row>')
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(sheet_rows)}</sheetData>'
        "</worksheet>"
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Alarmlar" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>"
    )
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", root_rels)
        zf.writestr("xl/workbook.xml", workbook)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        zf.writestr("xl/worksheets/sheet1.xml", sheet)
    return buf.getvalue()


def _xlsx_col(index: int) -> str:
    n = index
    letters = []
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters.append(chr(65 + rem))
    return "".join(reversed(letters)) or "A"
