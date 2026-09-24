"""Run a scan from ScanBody and return API-shaped results."""

from __future__ import annotations

import json
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.config import MAX_SYMBOLS_PER_SCAN
from app.database import PineScript
from app.services.pine_fibo import fibo_display_label
from app.services.pine_bias_ts import bias_ts_display_label
from app.services.pine_choch import choch_display_label
from app.services.pine_params import applied_inputs_summary, parse_saved_input_defaults
from app.services.pine_parser import extract_al_condition
from app.services.pine_storage import load_pine_content
from app.services.screener import FilterRule, ScanRequest, run_scan
from app.services.tv_export import build_tradingview_list
from app.utils.json_safe import json_safe


def scan_body_from_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize stored JSON config."""
    return {
        "universe": data.get("universe", "sp500"),
        "custom_symbols": data.get("custom_symbols", ""),
        "custom_source_universe": data.get("custom_source_universe"),
        "timeframe": data.get("timeframe", "1d"),
        "filters": data.get("filters") or [],
        "pine_script_id": data.get("pine_script_id"),
        "pine_condition_override": data.get("pine_condition_override"),
        "require_pine_al": bool(data.get("require_pine_al", False)),
        "pine_input_overrides": data.get("pine_input_overrides") or {},
        "max_symbols": int(data.get("max_symbols", 100)),
        "bist_data_provider": data.get("bist_data_provider"),
    }


def execute_scan_config(
    config: dict[str, Any],
    db: Session,
    progress_callback: Callable[[str, int, int, str], None] | None = None,
) -> dict[str, Any]:
    """Execute scan; returns same shape as POST /api/scan (without raising HTTPException)."""
    body = scan_body_from_dict(config)
    pine_condition = body.get("pine_condition_override")
    pine_source: str | None = None
    pine_code: str | None = None
    pine_label: str | None = None
    pine_input_overrides = dict(body.get("pine_input_overrides") or {})
    pine_script_id = body.get("pine_script_id")

    if pine_script_id:
        row = db.query(PineScript).filter(PineScript.id == pine_script_id).first()
        if not row:
            raise ValueError("Kayıtlı Pine script bulunamadı")
        pine_code = load_pine_content(row)
        saved = parse_saved_input_defaults(row.input_defaults)
        if not pine_input_overrides and saved:
            pine_input_overrides = saved
        detected = extract_al_condition(pine_code)
        if detected:
            pine_source = detected.source
            pine_condition = detected.condition
            pine_label = detected.display_condition
            if detected.source == "candle_green_first":
                pine_condition = detected.condition
                pine_label = fibo_display_label(pine_code)
            elif detected.source == "choch_bullish":
                pine_condition = detected.condition
                pine_label = choch_display_label(pine_code)
            elif detected.source == "bias_ts":
                pine_condition = detected.condition
                pine_label = bias_ts_display_label(pine_code, pine_input_overrides)
        else:
            pine_source = row.al_source
            pine_condition = pine_condition or row.al_condition
        if pine_source == "candle_green_first" and pine_code and not pine_label:
            pine_label = fibo_display_label(pine_code)
        if pine_source == "choch_bullish" and pine_code and not pine_label:
            pine_label = choch_display_label(pine_code)
        if pine_source == "bias_ts" and pine_code and not pine_label:
            pine_label = bias_ts_display_label(pine_code, pine_input_overrides)

    if body.get("require_pine_al") and not pine_condition:
        raise ValueError("Pine AL taraması için script veya koşul gerekli")

    filters = [
        FilterRule(
            id=f["id"],
            enabled=bool(f.get("enabled", True)),
            params=f.get("params") or {},
        )
        for f in body.get("filters") or []
    ]

    req = ScanRequest(
        universe=body["universe"],
        custom_symbols=body.get("custom_symbols") or "",
        custom_source_universe=body.get("custom_source_universe"),
        timeframe=body.get("timeframe") or "1d",
        filters=filters,
        pine_script_id=pine_script_id,
        require_pine_al=bool(body.get("require_pine_al")),
        pine_input_overrides=pine_input_overrides,
        max_symbols=min(int(body.get("max_symbols") or 100), MAX_SYMBOLS_PER_SCAN),
        bist_data_provider=body.get("bist_data_provider"),
    )

    results, stats = run_scan(
        req, pine_condition, pine_source, pine_code, progress_callback=progress_callback
    )

    pine_inputs_applied = (
        applied_inputs_summary(pine_code, pine_input_overrides)
        if pine_code and pine_input_overrides
        else []
    )

    tv_text = (
        build_tradingview_list([r.symbol for r in results], body["universe"])
        if results
        else ""
    )

    return json_safe(
        {
            "count": len(results),
            "universe": body["universe"],
            "timeframe": body["timeframe"],
            "pine_label": pine_label,
            "pine_source": pine_source,
            "pine_inputs_applied": pine_inputs_applied,
            "pine_mode": "first_green_bar" if pine_source == "candle_green_first" else None,
            "stats": {
                "requested": stats.requested,
                "downloaded": stats.downloaded,
                "skipped_inactive": stats.skipped_inactive,
                "scanned": stats.scanned,
                "matched": stats.matched,
                "skip_reasons": stats.skip_reasons,
            },
            "results": [
                {
                    "symbol": r.symbol,
                    "price": round(r.price, 2) if r.price == r.price else None,
                    "signals": r.signals,
                }
                for r in results
            ],
            "tradingview_symbols": tv_text.split("\n") if tv_text else [],
            "tradingview_text": tv_text,
        }
    )


def config_to_json(config: dict[str, Any]) -> str:
    return json.dumps(scan_body_from_dict(config), ensure_ascii=False)
