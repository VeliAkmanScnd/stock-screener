"""VIOP/Hisse ranking snapshot without Node (Yahoo via yfinance)."""

from __future__ import annotations

import json
import logging
import math
import threading
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

from app.config import BASE_DIR

logger = logging.getLogger(__name__)

CALC_DATA = BASE_DIR / "calc" / "data"
BIST_PATH = CALC_DATA / "screener-tickers.json"
LISTINGS_PATH = CALC_DATA / "us-listings.json"

_lock = threading.Lock()
_snapshot: dict = {
    "version": 4,
    "source": "python",
    "window": "20d",
    "complete": False,
    "updatedAt": "",
    "names": {"nasdaq": [], "nyse": []},
    "rows": [],
    "hype": {"timedOut": False},
}
_started = False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _listing_names() -> dict[str, list[dict[str, str]]]:
    listings = _load_json(LISTINGS_PATH, [])
    names = {"nasdaq": [], "nyse": []}
    for row in listings:
        exchange = str(row.get("exchange") or "").lower()
        if exchange not in names:
            continue
        ticker = str(row.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        names[exchange].append(
            {"ticker": ticker, "name": str(row.get("name") or ticker)}
        )
    return names


def _base_snapshot() -> dict:
    names = _listing_names()
    return {
        "version": 4,
        "source": "python",
        "window": "20d",
        "complete": False,
        "updatedAt": _now(),
        "names": names,
        "rows": [],
        "hype": {"timedOut": False},
    }


def get_snapshot() -> dict:
    with _lock:
        if not _snapshot["names"]["nasdaq"] and not _snapshot["names"]["nyse"]:
            _snapshot.update(_base_snapshot())
        return json.loads(json.dumps(_snapshot))


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = _mean(values)
    var = sum((value - avg) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(var)


def _stats_from_frame(ticker: str, exchange: str, currency: str, close, volume) -> dict | None:
    pair = pd.DataFrame({"close": close, "volume": volume}).dropna()
    pair = pair[pair["close"] > 0]
    if len(pair) < 6:
        return None
    window = pair.tail(21)
    notionals = (window["close"] * window["volume"].clip(lower=0)).tolist()
    closes = window["close"].tolist()
    returns = []
    for i in range(1, len(closes)):
        if closes[i - 1] > 0:
            returns.append(math.log(closes[i] / closes[i - 1]))
    if len(returns) < 5:
        return None
    last_close = float(closes[-1])
    last_notional = float(notionals[-1])
    avg_notional = _mean(notionals)
    abs_ret = [abs(value) for value in returns]
    long_abs = _mean(abs_ret)
    short_abs = _mean(abs_ret[-5:])
    return {
        "ticker": ticker,
        "avgVolumeTl": avg_notional,
        "lastVolumeTl": last_notional,
        "volatility": _stdev(returns) * math.sqrt(252) * 100,
        "dailyMove": long_abs * 100,
        "lastPrice": last_close,
        "marketCap": 0,
        "exchange": exchange,
        "currency": currency,
        "relativeVolume": (last_notional / avg_notional) if avg_notional > 0 else None,
        "shock": (short_abs / long_abs) if long_abs > 0 else None,
        "postHypeReturn1d": None,
        "postHypeReturn5d": None,
        "newsCount": None,
        "kapCount": None,
        "redditCount": None,
        "redditStatus": "unavailable",
        "trendsScore": None,
    }


def _series(data: pd.DataFrame, yahoo: str, field: str):
    if data is None or data.empty:
        return None
    cols = data.columns
    if isinstance(cols, pd.MultiIndex):
        # yfinance: (field, ticker) or (ticker, field)
        if field in cols.get_level_values(0) and yahoo in data[field].columns:
            return data[field][yahoo]
        try:
            return data[yahoo][field]
        except Exception:
            return None
    if field in data.columns:
        return data[field]
    return None


def _download_batch(items: list[dict]) -> list[dict]:
    if not items:
        return []
    symbols = [row["yahoo"] for row in items]
    try:
        data = yf.download(
            tickers=" ".join(symbols),
            period="3mo",
            interval="1d",
            auto_adjust=False,
            threads=True,
            progress=False,
            group_by="ticker",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("yfinance batch failed (%s): %s", len(symbols), exc)
        return []
    rows = []
    for item in items:
        yahoo = item["yahoo"]
        close = _series(data, yahoo, "Close")
        volume = _series(data, yahoo, "Volume")
        if close is None or volume is None:
            continue
        stats = _stats_from_frame(
            item["ticker"], item["exchange"], item["currency"], close, volume
        )
        if stats:
            rows.append(stats)
    return rows


def _publish(rows: list[dict], complete: bool) -> None:
    with _lock:
        _snapshot["rows"] = rows
        _snapshot["complete"] = complete
        _snapshot["updatedAt"] = _now()


def _refresh() -> None:
    names = _listing_names()
    with _lock:
        _snapshot["names"] = names
        _snapshot["updatedAt"] = _now()
        _snapshot["complete"] = False

    bist_tickers = [str(t).strip().upper() for t in _load_json(BIST_PATH, []) if str(t).strip()]
    bist_items = [
        {"ticker": t, "yahoo": f"{t}.IS", "exchange": "bist", "currency": "TL"}
        for t in bist_tickers
    ]
    us_items = []
    for row in _load_json(LISTINGS_PATH, []):
        exchange = str(row.get("exchange") or "").lower()
        ticker = str(row.get("ticker") or "").strip().upper()
        yahoo = str(row.get("yahoo") or ticker).strip()
        if exchange not in {"nasdaq", "nyse"} or not ticker:
            continue
        us_items.append(
            {
                "ticker": ticker,
                "yahoo": yahoo,
                "exchange": exchange,
                "currency": "USD",
            }
        )

    collected: list[dict] = []
    batches: list[list[dict]] = []
    for start in range(0, len(bist_items), 40):
        batches.append(bist_items[start : start + 40])
    for start in range(0, len(us_items), 40):
        batches.append(us_items[start : start + 40])

    for index, batch in enumerate(batches):
        collected.extend(_download_batch(batch))
        _publish(collected, complete=index == len(batches) - 1)
        logger.info(
            "Calc ranking %s/%s batches, %s rows",
            index + 1,
            len(batches),
            len(collected),
        )
    _publish(collected, complete=True)


def start_calc_screener() -> None:
    global _started
    if _started:
        return
    _started = True
    with _lock:
        _snapshot.update(_base_snapshot())
    threading.Thread(target=_refresh, name="calc-screener", daemon=True).start()
    logger.info(
        "Calc ranking: %s Nasdaq / %s NYSE isimleri yüklendi; hacim arka planda geliyor.",
        len(_snapshot["names"]["nasdaq"]),
        len(_snapshot["names"]["nyse"]),
    )
