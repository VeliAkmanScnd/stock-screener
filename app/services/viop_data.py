"""VIOP contract list + OHLCV — TradingView continuous only (TOASO1!, AEFES1!, …).

Never uses dayanak / cash equity (TOASO.IS). Missing continuous → symbol skipped.
"""

from __future__ import annotations

import json
import logging
from typing import Callable

import pandas as pd

from app.config import BASE_DIR
from app.services.ticker_format import (
    clean_viop_symbol,
    to_viop_continuous_symbol,
    viop_underlying,
)

logger = logging.getLogger(__name__)

OHLCV_COLS = ["Open", "High", "Low", "Close", "Volume"]
MIN_VIOP_SCAN_SYMBOLS = 40
SEED_PATH = BASE_DIR / "app" / "data" / "viop_contracts_seed.json"

# Calculator tickers → board underlyings used in F_* codes.
_SEED_TO_BOARD = {
    "BIST30": "XU030",
    "XAUTRY": "XAUTRYM",
}


def _normalize_frame(df: pd.DataFrame) -> pd.DataFrame | None:
    if df is None or df.empty:
        return None
    work = df.rename(columns=str.title)
    if not set(OHLCV_COLS).issubset(work.columns):
        return None
    out = work[OHLCV_COLS].dropna(how="all")
    if out.index.tz is not None:
        out = out.copy()
        out.index = out.index.tz_localize(None)
    return out if len(out) >= 10 else None


def expected_scan_underlyings() -> tuple[str, ...]:
    """Pay (47) + endeks (+ seed FX/emtia) mapped to board underlyings."""
    try:
        payload = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return tuple()
    out: list[str] = []
    for row in payload.get("contracts") or []:
        group = str(row.get("group") or "")
        ticker = str(row.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        # Scan focus: pay + endeks; keep FX/emtia from seed when board has them.
        if group not in ("pay", "endeks", "doviz", "emtia"):
            continue
        out.append(_SEED_TO_BOARD.get(ticker, ticker))
    return tuple(sorted(set(out)))


def fetch_viop_symbols_live() -> tuple[str, ...]:
    """Front-month F_ per underlying: seed pay/endeks + liquid board extras."""
    import borsapy as bp

    board = bp.VIOP()
    frames = [
        board.index_futures,
        board.stock_futures,
        board.currency_futures,
        board.commodity_futures,
    ]
    parts = [f for f in frames if f is not None and not f.empty]
    if not parts:
        raise ValueError("VIOP kontrat listesi boş")
    all_df = pd.concat(parts, ignore_index=True)
    if "code" not in all_df.columns:
        raise ValueError("VIOP tablo formatı beklenmedik")

    rows: list[tuple[str, str, float]] = []
    for _, row in all_df.iterrows():
        code = clean_viop_symbol(row.get("code") or "")
        if not code.startswith("F_"):
            continue
        und = viop_underlying(code)
        if not und:
            continue
        vol = float(row.get("volume_qty") or 0) or 0.0
        rows.append((und, code, vol))

    best: dict[str, tuple[str, float]] = {}
    for und, code, vol in rows:
        prev = best.get(und)
        if prev is None or vol > prev[1]:
            best[und] = (code, vol)

    expected = expected_scan_underlyings()
    chosen: dict[str, str] = {}
    missing: list[str] = []
    # Prefer seed universe (47 pay + endeks + …) when present on the board.
    for und in expected:
        hit = best.get(und)
        if hit:
            chosen[und] = hit[0]
        else:
            missing.append(und)
    # Keep other liquid board underlyings (extra pay/FX) not in seed.
    for und, (code, _) in best.items():
        chosen.setdefault(und, code)

    out = tuple(sorted(chosen.values()))
    if len(out) < MIN_VIOP_SCAN_SYMBOLS:
        raise ValueError(f"VIOP listesi eksik ({len(out)} < {MIN_VIOP_SCAN_SYMBOLS})")
    if missing:
        logger.warning(
            "VIOP seed underlyings missing on board (%d): %s",
            len(missing),
            ",".join(missing[:12]),
        )
    logger.info(
        "VIOP front contracts: %d (seed expected=%d, missing=%d)",
        len(out),
        len(expected),
        len(missing),
    )
    return out


def _pick_continuous(frames: dict[str, pd.DataFrame], continuous: str) -> pd.DataFrame | None:
    """Only accept frames keyed as continuous (…1!). Never cash dayanak."""
    if not continuous or not continuous.endswith("1!"):
        return None
    for key in (continuous, continuous.replace("!", ""), continuous.upper()):
        frame = frames.get(key)
        if frame is not None:
            return frame
    # Some downloads key without bang but equal to continuous stem+1
    stem = continuous[:-2] if continuous.endswith("1!") else continuous
    for key, frame in frames.items():
        k = str(key).strip().upper()
        if k == continuous.upper() or k == f"{stem}1!":
            return frame
    return None


def fetch_ohlcv_one_viop(symbol: str, timeframe: str) -> pd.DataFrame | None:
    """OHLCV from TradingView continuous only (e.g. TOASO1!)."""
    from app.services.borsapy_client import fetch_ohlcv_batch_borsapy

    continuous = to_viop_continuous_symbol(symbol)
    if not continuous.endswith("1!"):
        logger.warning("VIOP %s: sürekli sembol üretilemedi, atlandı", symbol)
        return None
    try:
        frames = fetch_ohlcv_batch_borsapy([continuous], timeframe)
    except Exception as exc:
        logger.warning("VIOP continuous %s failed: %s", continuous, exc)
        return None
    frame = _pick_continuous(frames, continuous)
    norm = _normalize_frame(frame) if frame is not None else None
    if norm is None:
        logger.warning(
            "VIOP %s → %s: sürekli vadeli veri yok (hisse/dayanak kullanılmaz)",
            clean_viop_symbol(symbol),
            continuous,
        )
    return norm


def fetch_ohlcv_batch_viop(
    symbols: list[str],
    timeframe: str,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> dict[str, pd.DataFrame]:
    """Batch OHLCV: every contract maps to its continuous (TOASO1!), never cash equity."""
    clean = [clean_viop_symbol(s) for s in symbols if clean_viop_symbol(s)]
    if not clean:
        return {}

    by_cont: dict[str, list[str]] = {}
    for code in clean:
        cont = to_viop_continuous_symbol(code)
        if not cont.endswith("1!"):
            logger.warning("VIOP %s: sürekli sembol yok, atlandı", code)
            continue
        by_cont.setdefault(cont, []).append(code)

    unique_cont = list(by_cont.keys())
    if not unique_cont:
        return {}

    cont_frames: dict[str, pd.DataFrame] = {}
    try:
        from app.services.borsapy_client import fetch_ohlcv_batch_borsapy

        fetched = fetch_ohlcv_batch_borsapy(
            unique_cont, timeframe, on_progress=on_progress
        )
        for cont in unique_cont:
            frame = _pick_continuous(fetched, cont)
            norm = _normalize_frame(frame) if frame is not None else None
            if norm is not None:
                cont_frames[cont] = norm
            else:
                # Direct key hit after normalize of any matching download key
                for key, raw in fetched.items():
                    if to_viop_continuous_symbol(key) == cont:
                        norm2 = _normalize_frame(raw)
                        if norm2 is not None:
                            cont_frames[cont] = norm2
                            break
    except Exception as exc:
        logger.warning("VIOP continuous batch failed: %s", exc)
        return {}

    out: dict[str, pd.DataFrame] = {}
    skipped = 0
    for cont, codes in by_cont.items():
        frame = cont_frames.get(cont)
        if frame is None:
            skipped += len(codes)
            logger.warning(
                "VIOP %s: sürekli vadeli yok — hisse/dayanak kullanılmaz, atlandı (%s)",
                cont,
                ",".join(codes[:3]),
            )
            continue
        for code in codes:
            out[code] = frame.copy()

    logger.info(
        "VIOP OHLCV %d / %d sürekli 1! (atlanan %d, dayanak yok)",
        len(out),
        len(clean),
        skipped,
    )
    return out
