"""Merge Pine script input defaults with user overrides for scanning."""

from __future__ import annotations

import json
from typing import Any

from app.services.pine_parser import PineInputParam, extract_pine_inputs


def _strip_quotes(val: str) -> str:
    v = val.strip()
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        return v[1:-1]
    return v


def merge_pine_inputs(pine_code: str, overrides: dict[str, Any] | None = None) -> dict[str, str]:
    """Return input name -> string value (defaults + overrides)."""
    merged = {p.name: p.default for p in extract_pine_inputs(pine_code)}
    if not overrides:
        return merged
    known = set(merged)
    for key, raw in overrides.items():
        if key not in known and key != "scan_side":
            continue
        if raw is None:
            continue
        if isinstance(raw, bool):
            merged[key] = "true" if raw else "false"
        else:
            merged[key] = str(raw).strip()
    return merged


def parse_saved_input_defaults(raw: str | None) -> dict[str, Any]:
    if not raw or not str(raw).strip():
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def effective_param_value(p: PineInputParam, saved: dict[str, Any] | None) -> str | bool | float | int:
    if saved and p.name in saved:
        return saved[p.name]
    return _display_default(p)


def pine_inputs_for_api(
    pine_code: str, saved_defaults: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in extract_pine_inputs(pine_code):
        d = param_to_api_dict(p)
        d["value"] = effective_param_value(p, saved_defaults)
        d["pine_default"] = d["default"]
        out.append(d)
    from app.services.pine_bias_ts import is_bias_ts_script

    if is_bias_ts_script(pine_code) and not any(p["name"] == "scan_side" for p in out):
        saved = (saved_defaults or {}).get("scan_side") or "buy"
        out.insert(
            0,
            {
                "name": "scan_side",
                "type": "string",
                "default": "buy",
                "value": str(saved).strip().lower() if saved else "buy",
                "pine_default": "buy",
                "label": "Tarama yönü",
                "group": "Sinyal filtreleri",
                "options": ["buy", "sell", "both"],
            },
        )
    return out


def param_to_api_dict(p: PineInputParam) -> dict[str, Any]:
    d: dict[str, Any] = {
        "name": p.name,
        "type": p.kind,
        "default": _display_default(p),
        "label": p.label,
        "group": p.group,
    }
    if p.options:
        d["options"] = p.options
    if p.minval is not None:
        d["min"] = p.minval
    if p.maxval is not None:
        d["max"] = p.maxval
    if p.step is not None:
        d["step"] = p.step
    return d


def _display_default(p: PineInputParam) -> str | bool | float | int:
    if p.kind == "bool":
        return _parse_bool(p.default, False)
    if p.kind == "int":
        try:
            return int(float(_strip_quotes(p.default)))
        except ValueError:
            return p.default
    if p.kind == "float":
        try:
            return float(_strip_quotes(p.default))
        except ValueError:
            return p.default
    return _strip_quotes(p.default)


def _parse_bool(val: str, default: bool) -> bool:
    v = _strip_quotes(str(val)).lower()
    if v in ("true", "1", "yes"):
        return True
    if v in ("false", "0", "no"):
        return False
    return default


def applied_inputs_summary(pine_code: str, overrides: dict[str, Any] | None) -> list[dict[str, str]]:
    """Non-default values only, for scan result header."""
    if not overrides:
        return []
    merged = merge_pine_inputs(pine_code, overrides)
    defaults = {p.name: p.default for p in extract_pine_inputs(pine_code)}
    out: list[dict[str, str]] = []
    for p in extract_pine_inputs(pine_code):
        if p.group == "Visual":
            continue
        cur = merged.get(p.name, "")
        if str(cur).strip() != str(defaults.get(p.name, "")).strip():
            out.append({"name": p.name, "label": p.label, "value": str(cur)})
    return out
