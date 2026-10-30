"""Weekend Bias tester vs alarm settings: sequential 47-pay revision report."""

from __future__ import annotations

import html
import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any

from app.database import OptimizeReviewMeta, OptimizeReviewRun, ScheduledScan, SessionLocal
from app.services.alarm_service import config_from_row, is_alarm_config, list_viop_pay_contracts, parse_contracts
from app.services.schedule_helpers import normalize_email_storage, parse_email_list
from app.utils.json_safe import json_safe

logger = logging.getLogger(__name__)

REVIEW_TOP = 5
REVIEW_EXTRA = 20
DEFAULT_REVIEW_EMAILS = "veliakman@gmail.com; akbastt@gmail.com"
DEFAULT_REVIEW_CONFIG: dict[str, Any] = {
    "timeframe": "30m",
    "period": "13mo",
    "mode": "quick",
    "side": "both",
    "max_combos": 500,
    "scan_all": False,
    "min_win_rate": 45,
    "max_drawdown": 18,
    "min_profit_factor": 1.3,
    "min_profit": 8,
    "min_trades": 10,
}

_run_lock = threading.Lock()
_cancel = threading.Event()
_thread: threading.Thread | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load_json(raw: str | None, fallback: Any) -> Any:
    try:
        return json.loads(raw or "")
    except json.JSONDecodeError:
        return fallback


def default_review_config() -> dict[str, Any]:
    return dict(DEFAULT_REVIEW_CONFIG)


def normalize_review_emails(raw: str | None) -> str:
    text = str(raw or "").replace(",", ";")
    if not text.strip():
        return ""
    return normalize_email_storage(parse_email_list(text))


def get_meta(db) -> OptimizeReviewMeta:
    row = db.query(OptimizeReviewMeta).filter(OptimizeReviewMeta.id == 1).first()
    if row:
        return row
    row = OptimizeReviewMeta(
        id=1,
        weekly_enabled=False,
        notify_email=True,
        email_to=DEFAULT_REVIEW_EMAILS,
        notify_telegram=True,
        telegram_to="",
        config_json=json.dumps(DEFAULT_REVIEW_CONFIG),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def review_settings(db) -> dict[str, Any]:
    from app.services.email_service import smtp_configured
    from app.services.telegram_service import telegram_configured

    meta = get_meta(db)
    cfg = _load_json(meta.config_json, {})
    if not isinstance(cfg, dict) or not cfg:
        cfg = default_review_config()
    return {
        "weekly_enabled": bool(meta.weekly_enabled),
        "notify_email": bool(getattr(meta, "notify_email", True)),
        "email_to": (meta.email_to or "").strip(),
        "notify_telegram": bool(getattr(meta, "notify_telegram", True)),
        "telegram_to": (getattr(meta, "telegram_to", None) or "").strip(),
        "smtp_configured": smtp_configured(),
        "telegram_configured": telegram_configured(),
        "config": {**default_review_config(), **cfg},
        "updated_at": meta.updated_at.isoformat() if meta.updated_at else None,
    }


def save_review_settings(
    db,
    *,
    weekly_enabled: bool | None = None,
    notify_email: bool | None = None,
    email_to: str | None = None,
    notify_telegram: bool | None = None,
    telegram_to: str | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    meta = get_meta(db)
    if weekly_enabled is not None:
        meta.weekly_enabled = bool(weekly_enabled)
    if notify_email is not None:
        meta.notify_email = bool(notify_email)
    if email_to is not None:
        meta.email_to = normalize_review_emails(email_to)
    if notify_telegram is not None:
        meta.notify_telegram = bool(notify_telegram)
    if telegram_to is not None:
        meta.telegram_to = (telegram_to or "").strip()
    if isinstance(config, dict) and config:
        merged = {**default_review_config(), **_load_json(meta.config_json, {}), **config}
        merged.pop("symbol", None)
        merged.pop("reference", None)
        meta.config_json = json.dumps(merged, ensure_ascii=False)
    meta.updated_at = _now()
    db.commit()
    return review_settings(db)


def latest_run(db) -> OptimizeReviewRun | None:
    return db.query(OptimizeReviewRun).order_by(OptimizeReviewRun.id.desc()).first()


def review_is_running() -> bool:
    with _run_lock:
        if _thread is not None and _thread.is_alive():
            return True
    db = SessionLocal()
    try:
        row = latest_run(db)
        return bool(row and row.status == "running")
    finally:
        db.close()


def run_to_dict(row: OptimizeReviewRun | None) -> dict[str, Any] | None:
    if not row:
        return None
    report = _load_json(row.report_json, {})
    symbols = report.get("symbols") if isinstance(report, dict) else []
    if not isinstance(symbols, list):
        symbols = []
    total = int(row.total_count or 0)
    done = int(row.done_count or 0)
    remaining = max(0, total - done)
    if row.status == "running" and row.current_symbol:
        remaining = max(0, total - done - 1)
    return {
        "id": row.id,
        "status": row.status,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "current_symbol": row.current_symbol,
        "done_count": done,
        "total_count": total,
        "remaining_count": remaining,
        "error": row.error_message,
        "config": _load_json(row.config_json, {}),
        "symbols": symbols,
        "summary": _run_summary(row.status, done, total, remaining, row.current_symbol, symbols),
    }


def _run_summary(status: str, done: int, total: int, remaining: int, current: str | None, symbols: list) -> str:
    recs = sum(len(s.get("recommendations") or []) for s in symbols if isinstance(s, dict))
    if status == "running":
        now = current or "—"
        return f"{done}/{total} pay bitti · şimdi {now} · kalan {remaining} · {recs} öneri"
    if status == "done":
        return f"{done}/{total} pay tamam · {recs} revizyon önerisi"
    if status == "cancelled":
        return f"Durduruldu · {done}/{total} pay işlendi · {recs} öneri"
    if status == "error":
        return f"Hata · {done}/{total} pay işlendi"
    return f"{done}/{total} pay"


def pine_overrides_from_public(params: dict[str, Any] | None) -> dict[str, Any]:
    p = params or {}
    return {
        "ha_len": p.get("ha_len"),
        "ha_len2": p.get("ha_len2"),
        "osc_len": p.get("osc_len"),
        "ha_htf": p.get("ha_htf") or "",
        "exitMode": p.get("exitMode") or p.get("exit_mode") or "Swing RR",
        "rrMult": p.get("rrMult", p.get("rr_mult", 1)),
        "swingBars": p.get("swingBars", p.get("swing_bars", 4)),
        "tp_pct": p.get("tp_pct", 2),
        "sl_pct": p.get("sl_pct", 1),
        "allow_long": p.get("allow_long", True),
        "allow_short": p.get("allow_short", True),
        "reverse_exit": p.get("reverse_exit", True),
        "require_bar": p.get("require_bar", False),
        "maxSame": p.get("maxSame", p.get("max_same", 1)),
    }


def reference_from_overrides(overrides: dict[str, Any] | None) -> dict[str, Any] | None:
    ov = overrides or {}
    if ov.get("ha_len") in (None, ""):
        return None
    return {
        "enabled": True,
        "ha_len": ov.get("ha_len"),
        "ha_len2": ov.get("ha_len2"),
        "osc_len": ov.get("osc_len"),
        "ha_htf": ov.get("ha_htf") or "30",
        "exit_mode": ov.get("exitMode") or ov.get("exit_mode") or "Swing RR",
        "rr_mult": ov.get("rrMult", ov.get("rr_mult", 1)),
        "swing_bars": ov.get("swingBars", ov.get("swing_bars", 4)),
        "tp_pct": ov.get("tp_pct", 2),
        "sl_pct": ov.get("sl_pct", 1),
        "reverse_exit": ov.get("reverse_exit", True),
        "require_bar": ov.get("require_bar", False),
        "max_same": ov.get("maxSame", ov.get("max_same", 1)),
    }


def alarm_for_contract(db, contract: str, timeframe: str | None = None) -> dict[str, Any] | None:
    want = (contract or "").strip().upper()
    tf = (timeframe or "").strip().lower()
    if not want:
        return None
    hits: list[tuple[int, dict[str, Any]]] = []
    for row in db.query(ScheduledScan).order_by(ScheduledScan.id.desc()).all():
        cfg = config_from_row(row)
        if not is_alarm_config(cfg):
            continue
        contracts = parse_contracts(cfg.get("custom_symbols") or "")
        if want not in {c.upper() for c in contracts}:
            continue
        item = {
            "id": row.id,
            "name": row.name,
            "enabled": bool(row.enabled),
            "timeframe": cfg.get("timeframe") or "15m",
            "pine_script_id": cfg.get("pine_script_id"),
            "overrides": cfg.get("pine_input_overrides") or {},
        }
        score = 0
        if item["enabled"]:
            score += 4
        if tf and str(item["timeframe"]).lower() == tf:
            score += 2
        hits.append((score, item))
    if not hits:
        return None
    hits.sort(key=lambda pair: (pair[0], pair[1]["id"]), reverse=True)
    return hits[0][1]


def improvement_reasons(row: dict[str, Any], ref: dict[str, Any] | None) -> list[str]:
    if not ref:
        return new_alarm_reasons(row)
    reasons: list[str] = []
    pf, rpf = float(row.get("profit_factor") or 0), float(ref.get("profit_factor") or 0)
    wr, rwr = float(row.get("win_rate") or 0), float(ref.get("win_rate") or 0)
    profit, rprofit = float(row.get("net_profit_pct") or 0), float(ref.get("net_profit_pct") or 0)
    dd, rdd = float(row.get("max_drawdown") or 0), float(ref.get("max_drawdown") or 0)
    if pf > rpf + 0.05:
        reasons.append(f"PF {rpf:.2f} → {pf:.2f}")
    if wr > rwr + 1:
        reasons.append(f"WR {rwr:.1f}% → {wr:.1f}%")
    if profit > rprofit + 0.8:
        reasons.append(f"Kâr {rprofit:.1f}% → {profit:.1f}%")
    if rdd > 0 and dd + 0.3 < rdd:
        reasons.append(f"DD {rdd:.1f}% → {dd:.1f}%")
    if dd > rdd + 3:
        return []
    return reasons


def highlight_keys(reasons: list[str] | None) -> list[str]:
    keys: list[str] = []
    for raw in reasons or []:
        text = str(raw)
        if text.startswith("WR"):
            keys.append("win_rate")
        elif text.startswith("PF"):
            keys.append("profit_factor")
        elif text.startswith("Kâr"):
            keys.append("net_profit_pct")
        elif text.startswith("DD"):
            keys.append("max_drawdown")
    return keys


def new_alarm_reasons(row: dict[str, Any]) -> list[str]:
    if int(row.get("trades") or 0) <= 0:
        return []
    if row.get("passed"):
        return ["Eşikleri geçti — yeni alarm için uygun"]
    return ["Taramanın en iyi seti — yeni alarm adayı"]


def _sort_proposals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda r: (
            not r["passed"],
            -len(r.get("reasons") or []),
            -float(r.get("profit_factor") or 0),
            -float(r.get("net_profit_pct") or 0),
            -float(r.get("win_rate") or 0),
        ),
    )


def propose_new_alarm_sets(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank scan rows into alarm-create suggestions when the pay has no alarm."""
    out: list[dict[str, Any]] = []
    for row in rows:
        reasons = new_alarm_reasons(row)
        if not reasons:
            continue
        out.append(_compact_row(row, reasons))
    return _sort_proposals(out)


def _compact_row(row: dict[str, Any], reasons: list[str]) -> dict[str, Any]:
    return {
        "rank": row.get("rank"),
        "passed": bool(row.get("passed")),
        "tag": row.get("tag") or "",
        "win_rate": row.get("win_rate"),
        "profit_factor": row.get("profit_factor"),
        "net_profit_pct": row.get("net_profit_pct"),
        "max_drawdown": row.get("max_drawdown"),
        "trades": row.get("trades"),
        "params": row.get("params") or {},
        "reasons": reasons,
        "highlights": highlight_keys(reasons),
        "pine_overrides": pine_overrides_from_public(row.get("params") or {}),
    }


def build_symbol_review(result: dict[str, Any], alarm: dict[str, Any] | None) -> dict[str, Any]:
    ref = result.get("reference") if isinstance(result.get("reference"), dict) else None
    rows = [r for r in (result.get("results") or []) if isinstance(r, dict) and r.get("tag") != "referans"]
    if not alarm:
        improved = propose_new_alarm_sets(rows)
        if improved:
            note = "Kayıtlı alarm yok; tarama sonuçlarından alarm kurma önerileri üretildi."
        else:
            note = "Kayıtlı alarm yok ve tarama önerilebilir set üretmedi."
    else:
        improved = []
        for row in rows:
            reasons = improvement_reasons(row, ref)
            if not reasons:
                continue
            improved.append(_compact_row(row, reasons))
        improved = _sort_proposals(improved)
        if ref:
            if not improved:
                note = "Mevcut alarm bu örneklemde önde veya eşit; zorunlu revizyon yok."
            else:
                note = f"Alarm «{alarm.get('name') or alarm.get('id')}» ile kıyaslandı."
        else:
            improved = propose_new_alarm_sets(rows)
            note = "Alarm kaydı var ama karşılaştırılacak parametre yok; tarama setleri alarm önerisi olarak listelendi."
    return {
        "symbol": result.get("symbol"),
        "name": result.get("name") or "",
        "status": "ok",
        "alarm": {"id": alarm.get("id"), "name": alarm.get("name"), "timeframe": alarm.get("timeframe")} if alarm else None,
        "reference": ref,
        "tested": result.get("tested") or 0,
        "passed": result.get("passed") or 0,
        "bars": result.get("bars") or 0,
        "note": note,
        "timeframe": result.get("timeframe") or "",
        "period": result.get("period") or "",
        "recommendations": improved[:REVIEW_TOP],
        "extras": improved[REVIEW_TOP : REVIEW_TOP + REVIEW_EXTRA],
    }


def _pay_universe() -> list[dict[str, str]]:
    return list_viop_pay_contracts()


def _update_run(db, row: OptimizeReviewRun, **kwargs: Any) -> None:
    for key, value in kwargs.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)


def _append_symbol(db, row: OptimizeReviewRun, item: dict[str, Any]) -> None:
    report = _load_json(row.report_json, {"symbols": []})
    symbols = list(report.get("symbols") or [])
    symbols = [s for s in symbols if not (isinstance(s, dict) and s.get("symbol") == item.get("symbol"))]
    symbols.append(item)
    report["symbols"] = symbols
    row.report_json = json.dumps(json_safe(report), ensure_ascii=False)
    row.done_count = len(symbols)
    db.commit()


def cancel_review() -> dict[str, Any]:
    _cancel.set()
    db = SessionLocal()
    try:
        row = latest_run(db)
        if row and row.status == "running":
            row.status = "cancelling"
            db.commit()
        return run_to_dict(latest_run(db)) or {"status": "idle"}
    finally:
        db.close()


def start_review(config: dict[str, Any] | None = None, *, resume: bool = False) -> dict[str, Any]:
    global _thread
    from app.services.bias_optimizer import OptimizeCancelled, optimize_job_is_running, run_bias_optimize

    with _run_lock:
        if _thread is not None and _thread.is_alive():
            raise RuntimeError("Bir alarm revizyon taraması zaten çalışıyor")
    if not resume and optimize_job_is_running():
        raise RuntimeError("Tekil tester taraması çalışıyor; bitince veya durdurunca başlatın")
    db = SessionLocal()
    try:
        pays = _pay_universe()
        if not pays:
            raise RuntimeError("VIOP pay listesi boş")
        settings = review_settings(db)
        body_cfg = {**default_review_config(), **(settings.get("config") or {}), **(config or {})}
        body_cfg.pop("symbol", None)
        body_cfg.pop("reference", None)
        row = latest_run(db) if resume else None
        if resume:
            if not row or row.status != "running":
                return run_to_dict(row) or {"status": "idle"}
            body_cfg = {**default_review_config(), **_load_json(row.config_json, {})}
            body_cfg.pop("symbol", None)
            body_cfg.pop("reference", None)
            report = _load_json(row.report_json, {})
            done_syms = {s.get("symbol") for s in (report.get("symbols") or []) if isinstance(s, dict)}
        else:
            row = OptimizeReviewRun(
                status="running",
                started_at=_now(),
                current_symbol=None,
                done_count=0,
                total_count=len(pays),
                config_json=json.dumps(body_cfg, ensure_ascii=False),
                report_json=json.dumps({"symbols": []}),
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            done_syms = set()
        run_id = row.id
    finally:
        db.close()

    def worker() -> None:
        _cancel.clear()
        try:
            for item in pays:
                if _cancel.is_set():
                    break
                contract = item["contract"]
                if contract in done_syms:
                    continue
                dbw = SessionLocal()
                try:
                    run = dbw.query(OptimizeReviewRun).filter(OptimizeReviewRun.id == run_id).first()
                    if not run:
                        return
                    _update_run(dbw, run, status="running", current_symbol=contract)
                    alarm = alarm_for_contract(dbw, contract, str(body_cfg.get("timeframe") or ""))
                    ref = reference_from_overrides((alarm or {}).get("overrides"))
                    body = dict(body_cfg)
                    body["symbol"] = contract
                    if ref:
                        body["reference"] = ref
                    review = None
                    try:
                        result = run_bias_optimize(body, should_stop=_cancel.is_set)
                        if result.get("cancelled") or _cancel.is_set():
                            break
                        result["symbol"] = contract
                        result["name"] = item.get("name") or item.get("ticker") or contract
                        review = build_symbol_review(result, alarm)
                    except OptimizeCancelled:
                        break
                    except Exception as exc:
                        logger.exception("review symbol failed %s", contract)
                        review = {
                            "symbol": contract,
                            "name": item.get("name") or item.get("ticker") or contract,
                            "status": "error",
                            "error": str(exc),
                            "alarm": {"id": alarm.get("id"), "name": alarm.get("name")} if alarm else None,
                            "recommendations": [],
                            "extras": [],
                            "note": "Tarama hata verdi",
                        }
                    if review:
                        run = dbw.query(OptimizeReviewRun).filter(OptimizeReviewRun.id == run_id).first()
                        if run:
                            _append_symbol(dbw, run, review)
                            done_syms.add(contract)
                finally:
                    dbw.close()
            dbw = SessionLocal()
            try:
                run = dbw.query(OptimizeReviewRun).filter(OptimizeReviewRun.id == run_id).first()
                if run:
                    if _cancel.is_set():
                        _update_run(dbw, run, status="cancelled", current_symbol=None, finished_at=_now())
                    else:
                        _update_run(dbw, run, status="done", current_symbol=None, finished_at=_now())
            finally:
                dbw.close()
            try:
                notify_review_finished(run_id)
            except Exception:
                logger.exception("Review email failed")
        except Exception as exc:
            logger.exception("optimize review failed")
            dbw = SessionLocal()
            try:
                run = dbw.query(OptimizeReviewRun).filter(OptimizeReviewRun.id == run_id).first()
                if run:
                    _update_run(dbw, run, status="error", error_message=str(exc), finished_at=_now(), current_symbol=None)
            finally:
                dbw.close()
            try:
                notify_review_finished(run_id)
            except Exception:
                logger.exception("Review email failed")

    with _run_lock:
        _thread = threading.Thread(target=worker, name="bias-review", daemon=True)
        _thread.start()
    db = SessionLocal()
    try:
        return run_to_dict(db.query(OptimizeReviewRun).filter(OptimizeReviewRun.id == run_id).first()) or {}
    finally:
        db.close()


def _fmt_metric(value: Any, digits: int = 1) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "—"


def build_review_email(payload: dict[str, Any]) -> tuple[str, str, str]:
    status = payload.get("status") or ""
    done = int(payload.get("done_count") or 0)
    total = int(payload.get("total_count") or 0)
    symbols = [s for s in (payload.get("symbols") or []) if isinstance(s, dict)]
    rec_n = sum(len(s.get("recommendations") or []) for s in symbols)
    if status == "done":
        title = "Alarm revizyonu tamamlandı"
    elif status == "cancelled":
        title = "Alarm revizyonu durduruldu"
    else:
        title = "Alarm revizyonu hata ile bitti"
    subject = f"{title} · {done}/{total} pay · {rec_n} öneri"
    lines = [payload.get("summary") or title, ""]
    html_parts = [
        f"<h2>{html.escape(title)}</h2>",
        f"<p>{html.escape(payload.get('summary') or '')}</p>",
    ]
    if not symbols:
        lines.append("Raporda pay yok.")
        html_parts.append("<p>Raporda pay yok.</p>")
        return subject, "\n".join(lines), "".join(html_parts)
    for item in symbols:
        recs = item.get("recommendations") or []
        extras = item.get("extras") or []
        head = f"{item.get('symbol') or ''} · {item.get('name') or ''} · {len(recs)} öneri"
        if extras:
            head += f" · +{len(extras)} diğer"
        lines.append(head)
        if item.get("note"):
            lines.append(f"  {item['note']}")
        html_parts.append(f"<h3>{html.escape(head)}</h3>")
        if item.get("note"):
            html_parts.append(f"<p>{html.escape(str(item['note']))}</p>")
        html_parts.append("<ul>")
        for rec in recs:
            hl = set(rec.get("highlights") or [])
            bits = [
                ("WR", f"{_fmt_metric(rec.get('win_rate'))}%", "win_rate"),
                ("PF", _fmt_metric(rec.get("profit_factor"), 2), "profit_factor"),
                ("Kâr", f"{_fmt_metric(rec.get('net_profit_pct'))}%", "net_profit_pct"),
                ("DD", f"{_fmt_metric(rec.get('max_drawdown'))}%", "max_drawdown"),
            ]
            metric_plain = " · ".join(f"{label} {val}" for label, val, _key in bits)
            metric_html = " · ".join(
                f"<strong>{html.escape(label)} {html.escape(val)}</strong>" if key in hl else f"{html.escape(label)} {html.escape(val)}"
                for label, val, key in bits
            )
            why = " · ".join(str(x) for x in (rec.get("reasons") or []) if x)
            lines.append(f"  {metric_plain} · {rec.get('trades') or 0} işlem")
            if why:
                lines.append(f"  {why}")
            why_html = ""
            if why:
                why_html = "<br>" + " · ".join(
                    f"<strong>{html.escape(str(x))}</strong>" if highlight_keys([x]) else html.escape(str(x))
                    for x in (rec.get("reasons") or [])
                    if x
                )
            html_parts.append(f"<li>{metric_html} · {int(rec.get('trades') or 0)} işlem{why_html}</li>")
        html_parts.append("</ul>")
        lines.append("")
    return subject, "\n".join(lines).strip(), "".join(html_parts)


def _telegram_chunks(text: str, limit: int = 3500) -> list[str]:
    rest = (text or "").strip()
    if not rest:
        return []
    chunks: list[str] = []
    while rest:
        if len(rest) <= limit:
            chunks.append(rest)
            break
        cut = rest.rfind("\n\n", 0, limit)
        if cut < 80:
            cut = rest.rfind("\n", 0, limit)
        if cut < 80:
            cut = limit
        chunks.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    return chunks


def notify_review_finished(run_id: int, *, force: bool = False) -> dict[str, Any]:
    from app.services.email_service import send_tv_list_email, smtp_configured
    from app.services.telegram_service import parse_chat_ids, send_telegram_text, telegram_configured

    db = SessionLocal()
    try:
        settings = review_settings(db)
        run = db.query(OptimizeReviewRun).filter(OptimizeReviewRun.id == run_id).first()
        payload = run_to_dict(run) or {}
    finally:
        db.close()
    want_email = bool(settings.get("notify_email"))
    want_telegram = bool(settings.get("notify_telegram"))
    if not force and not want_email and not want_telegram:
        logger.info("Review notify skipped — all channels off")
        return {"ok": False, "skipped": "notify off"}
    if force and not want_email and not want_telegram:
        want_email = True
    subject, body, _body_html = build_review_email(payload)
    sent: dict[str, Any] = {"ok": True, "email": False, "telegram": 0}
    errors: list[str] = []

    if want_email:
        to_address = normalize_review_emails(settings.get("email_to") or "")
        if not to_address:
            errors.append("E-posta alıcısı yok")
        elif not smtp_configured():
            errors.append("SMTP yok (.env: SMTP_HOST, SMTP_FROM) — zamanlanmış tarama ile aynı ayar")
        else:
            try:
                send_tv_list_email(
                    to_address=to_address,
                    subject=subject,
                    body_text=body,
                    tv_list_text=body + "\n",
                    filename=f"alarm_revizyon_{run_id}.txt",
                )
                sent["email"] = True
                sent["to"] = to_address
            except Exception as exc:
                errors.append(f"e-posta: {exc}")
                logger.exception("Review email failed")

    if want_telegram:
        extra = (settings.get("telegram_to") or "").strip()
        chats = parse_chat_ids(extra)
        if not chats and not telegram_configured():
            errors.append("Telegram yok (.env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)")
        else:
            from app.config import TELEGRAM_CHAT_ID

            targets = chats or parse_chat_ids(TELEGRAM_CHAT_ID)
            if not targets:
                errors.append("Telegram chat id yok")
            else:
                try:
                    n = 0
                    for chat_id in targets:
                        for chunk in _telegram_chunks(f"{subject}\n\n{body}"):
                            send_telegram_text(chat_id, chunk, parse_mode=None)
                            n += 1
                    sent["telegram"] = n
                except Exception as exc:
                    errors.append(f"telegram: {exc}")
                    logger.exception("Review telegram failed")

    if errors and not sent["email"] and not sent["telegram"]:
        raise RuntimeError(" · ".join(errors))
    if errors:
        sent["warnings"] = errors
    return sent


def maybe_resume_review() -> None:
    db = SessionLocal()
    try:
        row = latest_run(db)
        if not row or row.status != "running":
            return
        logger.info("Resuming alarm revision review id=%s", row.id)
    finally:
        db.close()
    try:
        start_review(resume=True)
    except RuntimeError:
        pass


def weekly_tick() -> None:
    db = SessionLocal()
    try:
        settings = review_settings(db)
        if not settings.get("weekly_enabled"):
            logger.info("Friday review skipped — weekly toggle off")
            return
        if review_is_running():
            logger.info("Friday review skipped — already running")
            return
        start_review(settings.get("config"))
        logger.info("Friday 19:00 alarm revision review started")
    except Exception:
        logger.exception("Friday review failed to start")
    finally:
        db.close()
