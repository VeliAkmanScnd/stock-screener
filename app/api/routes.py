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
    bist_data_provider: str | None = None


class TradingViewExportBody(BaseModel):
    symbols: list[str] = Field(default_factory=list)
    universe: str = "sp500"


@router.get("/api/config/providers")
def api_data_providers():
    from app.config import BIST_DATA_PROVIDER, BIST_TD_FALLBACK
    from app.services.bist_data import active_provider_label, bist_provider_options
    from app.services.borsapy_client import (
        is_borsapy_available,
        tradingview_auth_configured,
    )
    from app.services.twelvedata_client import is_configured as td_configured

    daily_provider = active_provider_label("1d")
    return {
        "bist_provider": daily_provider,
        "bist_ready": True,
        "bist_data_provider_setting": BIST_DATA_PROVIDER,
        "bist_providers": bist_provider_options(),
        "default_bist_provider": BIST_DATA_PROVIDER,
        "borsapy_installed": is_borsapy_available(),
        "tradingview_auth_configured": tradingview_auth_configured(),
        "twelvedata_configured": td_configured(),
        "bist_td_fallback": BIST_TD_FALLBACK,
        "us_provider": "yfinance",
        "verda_note": (
            "BIST: tarama öncesi veri kaynağını seçebilirsiniz. borsapy + TradingView canlı "
            "veri için .env içinde TRADINGVIEW_SESSION_ID ve TRADINGVIEW_SESSION_SIGN gerekir."
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
        "viop": "VIOP (vadeli kontratlar)",
        "binance": "Binance Spot (USDT)",
        "custom": "Özel liste",
    }
    if universe == "binance":
        min_count = 50
    elif universe == "viop":
        min_count = 5
    else:
        min_count = 100
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

    from app.services.bist_data import active_provider_label

    bist_provider = active_provider_label("1d") if universe == "bist" else None
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
        "bist_provider": bist_provider,
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
        al_condition = r.al_condition
        al_source = r.al_source
        if not al_condition and (path_ok or content_ok):
            content = load_pine_content(r)
            al = extract_al_condition(content)
            if al:
                al_source = al.source
                if al.source in ("candle_green_first", "merged_triple", "choch_bullish", "bias_ts"):
                    al_condition = al.display_condition
                else:
                    al_condition = al.display_condition or al.condition
                r.al_condition = al_condition
                r.al_source = al_source
                db.commit()
        out.append(
            {
                "id": r.id,
                "name": r.name,
                "filename": r.filename,
                "al_condition": al_condition,
                "al_source": al_source,
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
        if al.source in ("candle_green_first", "merged_triple", "choch_bullish", "bias_ts"):
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
    if al and al.source == "bias_ts":
        msg = (
            "Bias × Trend Strength motoru aktif. "
            "Son barda BUY (veya seçilen yön) taranır. VIOP için evreni VIOP seçin."
        )
    elif al and al.source == "merged_triple":
        msg = (
            f"Merged-Triple motoru aktif ({len(params)} parametre). "
            "BUY sinyali tam confluence ile taranır."
        )
    elif al and al.source == "choch_bullish":
        msg = "ChoCh ↑ sinyali: yükseliş yapısı değişimi (ilk bar) taranacak."
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
def api_scan(body: ScanBody):
    if body.require_pine_al and not body.pine_script_id and not body.pine_condition_override:
        raise HTTPException(400, "Pine AL taraması için script veya koşul gerekli")

    from app.services.scan_jobs import start_scan_job

    job_id = start_scan_job(body.model_dump())
    return {"job_id": job_id, "status": "running"}


@router.get("/api/scan/jobs/{job_id}")
def api_scan_job(job_id: str):
    from app.services.scan_jobs import get_scan_job

    job = get_scan_job(job_id)
    if not job:
        raise HTTPException(404, "Tarama bulunamadı veya süresi doldu")
    return job


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
