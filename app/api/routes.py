from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.api.auth_deps import get_current_user
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import MAX_SYMBOLS_PER_SCAN
from app.services.twelvedata_client import TwelveDataError
from app.database import PineScript, get_db
from app.services.data_fetcher import (
    get_universe_count,
    get_universe_meta,
    get_universe_symbols,
    parse_symbol_list,
    refresh_universe_cache,
)
from app.services.pine_fibo import fibo_display_label
from app.services.pine_params import (
    applied_inputs_summary,
    parse_saved_input_defaults,
    pine_inputs_for_api,
)
from app.services.pine_parser import extract_al_condition
from app.services.pine_storage import load_pine_content, save_pine_script
from app.services.screener import FilterRule, ScanRequest, run_scan
from app.services.tv_export import build_tradingview_list
from app.utils.json_safe import json_safe

router = APIRouter(dependencies=[Depends(get_current_user)])


class FilterRuleModel(BaseModel):
    id: str
    enabled: bool = True
    params: dict[str, Any] = Field(default_factory=dict)


class ScanBody(BaseModel):
    universe: str = "sp500"
    custom_symbols: str = ""
    custom_source_universe: str | None = None
    timeframe: str = "1d"
    filters: list[FilterRuleModel] = Field(default_factory=list)
    pine_script_id: int | None = None
    pine_condition_override: str | None = None
    require_pine_al: bool = False
    pine_input_overrides: dict[str, Any] = Field(default_factory=dict)
    max_symbols: int = 100


class TradingViewExportBody(BaseModel):
    symbols: list[str] = Field(default_factory=list)
    universe: str = "sp500"


@router.get("/api/config/providers")
def api_data_providers():
    return {
        "bist_provider": "yfinance",
        "bist_ready": True,
        "us_provider": "yfinance",
        "verda_note": (
            "Borsa İstanbul VERDA API yalnızca yetkili kurumlar için dosya indirme sunar; "
            "canlı BIST OHLCV taraması Yahoo Finance (.IS) ile yapılır."
        ),
    }


@router.get("/api/symbols/sp500")
def api_sp500_count():
    return api_universe_info("sp500")


@router.get("/api/symbols/info")
def api_universe_info(universe: str = "sp500", refresh: bool = False):
    labels = {
        "sp500": "S&P 500",
        "nasdaq": "NASDAQ",
        "nyse": "NYSE",
        "all_us": "NASDAQ + NYSE + S&P 500",
        "bist": "BIST (Borsa İstanbul)",
        "binance": "Binance Spot (USDT)",
        "custom": "Özel liste",
    }
    min_count = 50 if universe == "binance" else 100
    if universe == "custom":
        return {
            "universe": universe,
            "label": labels["custom"],
            "count": 0,
            "sample": [],
            "fetch_ok": True,
            "bist_requires_api_key": False,
        }

    if refresh:
        try:
            refresh_universe_cache(universe if universe != "all_us" else None)
        except Exception as exc:
            return {
                "universe": universe,
                "label": labels.get(universe, universe),
                "count": 0,
                "sample": [],
                "fetch_ok": False,
                "message": str(exc),
            }

    meta = get_universe_meta(universe)
    try:
        symbols = get_universe_symbols(universe)
        count = len(symbols)
        sample = symbols[:15]
        fetch_ok = meta.ok and count > min_count
    except Exception as exc:
        count = 0
        sample = []
        fetch_ok = False
        meta = type(meta)(ok=False, source=universe, message=str(exc), cached=False)

    return {
        "universe": universe,
        "label": labels.get(universe, universe),
        "count": count,
        "sample": sample,
        "fetch_ok": fetch_ok,
        "source": meta.source,
        "cached": meta.cached,
        "message": meta.message,
        "bist_requires_api_key": False,
        "bist_provider": "yfinance" if universe == "bist" else None,
        "binance_provider": "binance" if universe == "binance" else None,
    }


@router.post("/api/symbols/refresh")
def api_refresh_symbols(universe: str = "all_us"):
    try:
        counts = refresh_universe_cache(universe if universe != "all_us" else None)
        return {"ok": True, "counts": counts}
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc


@router.get("/api/pine/scripts")
def list_pine_scripts(db: Session = Depends(get_db)):
    rows = db.query(PineScript).order_by(PineScript.created_at.desc()).all()
    out = []
    for r in rows:
        path_ok = bool(r.file_path) and Path(r.file_path).is_file()
        content_ok = bool(r.pine_content and r.pine_content.strip())
        out.append(
            {
                "id": r.id,
                "name": r.name,
                "filename": r.filename,
                "al_condition": r.al_condition,
                "al_source": r.al_source,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "available": path_ok or content_ok,
            }
        )
    return out


@router.get("/api/pine/scripts/{script_id}")
def get_pine_script(script_id: int, db: Session = Depends(get_db)):
    row = db.query(PineScript).filter(PineScript.id == script_id).first()
    if not row:
        raise HTTPException(404, "Script not found")
    content = load_pine_content(row)
    saved = parse_saved_input_defaults(row.input_defaults)
    return {
        "id": row.id,
        "name": row.name,
        "filename": row.filename,
        "content": content,
        "al_condition": row.al_condition,
        "al_source": row.al_source,
        "saved_defaults": saved,
        "has_saved_defaults": bool(saved),
        "parameters": pine_inputs_for_api(content, saved),
    }


class PineInputDefaultsBody(BaseModel):
    overrides: dict[str, Any] = Field(default_factory=dict)


@router.put("/api/pine/scripts/{script_id}/input-defaults")
def save_pine_input_defaults(
    script_id: int, body: PineInputDefaultsBody, db: Session = Depends(get_db)
):
    import json

    row = db.query(PineScript).filter(PineScript.id == script_id).first()
    if not row:
        raise HTTPException(404, "Script not found")
    content = load_pine_content(row)
    known = {p["name"] for p in pine_inputs_for_api(content)}
    cleaned = {k: v for k, v in body.overrides.items() if k in known}
    row.input_defaults = json.dumps(cleaned) if cleaned else None
    db.commit()
    return {
        "ok": True,
        "saved_defaults": cleaned,
        "has_saved_defaults": bool(cleaned),
        "message": "Parametreler varsayılan olarak kaydedildi.",
    }


@router.delete("/api/pine/scripts/{script_id}/input-defaults")
def clear_pine_input_defaults(script_id: int, db: Session = Depends(get_db)):
    row = db.query(PineScript).filter(PineScript.id == script_id).first()
    if not row:
        raise HTTPException(404, "Script not found")
    row.input_defaults = None
    db.commit()
    content = load_pine_content(row)
    return {
        "ok": True,
        "parameters": pine_inputs_for_api(content),
        "message": "Kayıtlı varsayılanlar silindi; Pine dosyası değerleri kullanılıyor.",
    }


@router.delete("/api/pine/scripts/{script_id}")
def delete_pine_script(script_id: int, db: Session = Depends(get_db)):
    row = db.query(PineScript).filter(PineScript.id == script_id).first()
    if not row:
        raise HTTPException(404, "Script not found")
    path = Path(row.file_path)
    if path.exists():
        path.unlink()
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/api/pine/upload")
async def upload_pine(
    file: UploadFile = File(...),
    name: str = Form(""),
    db: Session = Depends(get_db),
):
    if not file.filename or not file.filename.lower().endswith((".txt", ".pine", ".pinescript")):
        raise HTTPException(400, "Lütfen .txt veya .pine uzantılı bir dosya yükleyin")

    raw = await file.read()
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        content = raw.decode("latin-1", errors="replace")

    al = extract_al_condition(content)
    display_name = (name or Path(file.filename).stem).strip() or "script"

    stored_condition = None
    if al:
        if al.source in ("candle_green_first", "merged_triple"):
            stored_condition = al.display_condition
        else:
            stored_condition = al.display_condition or al.condition

    row = save_pine_script(
        db,
        content=content,
        display_name=display_name,
        original_filename=file.filename,
        al_condition=stored_condition,
        al_source=al.source if al else None,
    )

    params = pine_inputs_for_api(content)
    msg = "AL koşulu otomatik bulundu."
    if al and al.source == "merged_triple":
        msg = (
            f"Merged-Triple motoru aktif ({len(params)} parametre). "
            "BUY sinyali tam confluence ile taranır."
        )
    elif al and al.first_bar_only:
        msg = "Yeşil mum sinyali: sadece yeşile DÖNÜŞEN ilk bar (alış) taranacak."
    elif not al:
        msg = "AL koşulu otomatik bulunamadı; taramada manuel koşul girebilirsiniz."

    return {
        "id": row.id,
        "name": row.name,
        "al_detected": al is not None,
        "al_condition": al.display_condition if al and al.display_condition else row.al_condition,
        "al_source": row.al_source,
        "first_bar_only": al.first_bar_only if al else False,
        "parameters": params,
        "message": msg,
    }


@router.post("/api/pine/preview")
async def preview_pine(file: UploadFile = File(...)):
    raw = await file.read()
    content = raw.decode("utf-8", errors="replace")
    al = extract_al_condition(content)
    label = None
    if al and al.source == "candle_green_first":
        label = fibo_display_label(content)
    elif al and al.display_condition:
        label = al.display_condition
    return {
        "al_detected": al is not None,
        "al_condition": label,
        "al_source": al.source if al else None,
        "variable": al.variable_name if al else None,
        "parameters": pine_inputs_for_api(content),
    }


@router.post("/api/scan")
def api_scan(body: ScanBody, db: Session = Depends(get_db)):
    pine_condition = body.pine_condition_override
    pine_source: str | None = None
    pine_code: str | None = None

    pine_label: str | None = None

    pine_input_overrides = dict(body.pine_input_overrides or {})

    if body.pine_script_id:
        row = db.query(PineScript).filter(PineScript.id == body.pine_script_id).first()
        if not row:
            raise HTTPException(404, "Kayıtlı Pine script bulunamadı")
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
        else:
            pine_source = row.al_source
            pine_condition = pine_condition or row.al_condition
        if pine_source == "candle_green_first" and pine_code and not pine_label:
            pine_label = fibo_display_label(pine_code)

    if body.require_pine_al and not pine_condition:
        raise HTTPException(400, "Pine AL taraması için script veya koşul gerekli")

    filters = [FilterRule(id=f.id, enabled=f.enabled, params=f.params) for f in body.filters]

    req = ScanRequest(
        universe=body.universe,
        custom_symbols=body.custom_symbols,
        custom_source_universe=body.custom_source_universe,
        timeframe=body.timeframe,
        filters=filters,
        pine_script_id=body.pine_script_id,
        require_pine_al=body.require_pine_al,
        pine_input_overrides=pine_input_overrides,
        max_symbols=min(body.max_symbols, MAX_SYMBOLS_PER_SCAN),
    )

    try:
        results, stats = run_scan(req, pine_condition, pine_source, pine_code)
    except TwelveDataError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"Tarama hatası: {exc}") from exc

    pine_inputs_applied = (
        applied_inputs_summary(pine_code, pine_input_overrides)
        if pine_code and pine_input_overrides
        else []
    )

    return json_safe(
        {
            "count": len(results),
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
            "tradingview_symbols": build_tradingview_list(
                [r.symbol for r in results], body.universe
            ).split("\n")
            if results
            else [],
        }
    )


@router.post("/api/export/tradingview")
def export_tradingview_list(body: TradingViewExportBody):
    if not body.symbols:
        raise HTTPException(400, "Dışa aktarılacak sembol yok")
    text = build_tradingview_list(body.symbols, body.universe)
    if not text.strip():
        raise HTTPException(400, "Dışa aktarılacak sembol yok")
    safe_univ = (body.universe or "list").replace("/", "-")[:32]
    filename = f"tradingview_{safe_univ}.txt"
    return PlainTextResponse(
        content=text + ("\n" if not text.endswith("\n") else ""),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
