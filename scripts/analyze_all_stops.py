"""Deep analysis of all stop/losing trades from MT5 strategy tester report."""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

REPORT = Path(r"C:\Users\Dell\Downloads\aralık-haziran-6596-usd.html")
NEWS_DIR = Path(__file__).resolve().parents[1] / "storage" / "news_calendar"
OUT = Path(__file__).resolve().parents[1] / "storage" / "strategy_tester" / "stop_analysis_deep.json"

STOP_LOSS_THRESHOLD = -100


def read_html(path: Path) -> str:
    raw = path.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    return raw.decode("utf-8", errors="replace")


def parse_mt5_dt(s: str) -> datetime:
    return datetime.strptime(s.strip(), "%Y.%m.%d %H:%M:%S")


def parse_news_time(date_str: str, time_str: str) -> datetime | None:
    if not time_str:
        return None
    m = re.match(r"(\d{1,2}):(\d{2})(am|pm)", time_str.strip().lower())
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2))
    if m.group(3) == "pm" and hour != 12:
        hour += 12
    if m.group(3) == "am" and hour == 12:
        hour = 0
    d = datetime.strptime(date_str, "%Y-%m-%d")
    return d.replace(hour=hour, minute=minute)


def load_news_events() -> list[dict]:
    events = []
    for path in sorted(NEWS_DIR.glob("2026-*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for ev in data.get("events", []):
            dt = parse_news_time(ev["date"], ev.get("time") or "")
            if dt:
                events.append({**ev, "datetime": dt})
    # Fill NFP bundle times (missing in export)
    by_date: dict[str, list] = defaultdict(list)
    for ev in events:
        by_date[ev["date"]].append(ev)
    for date, evs in by_date.items():
        bundle = [e for e in evs if e.get("time")]
        if not bundle:
            continue
        t = min(e["datetime"] for e in bundle)
        for ev in evs:
            if not ev.get("time") and any(
                k in ev.get("event", "").lower()
                for k in ("non-farm", "unemployment rate", "average hourly")
            ):
                ev["datetime"] = t
                ev["time"] = t.strftime("%I:%M%p").lstrip("0").lower()
    return [e for e in events if "datetime" in e]


def parse_deals(html: str) -> list[dict]:
    pattern = re.compile(
        r'<tr bgcolor="#[^"]+" align=right><td>(\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2})</td>'
        r"<td>(\d+)</td><td>([^<]*)</td><td>([^<]*)</td><td>([^<]*)</td>"
        r"<td>([^<]*)</td><td>([^<]*)</td><td>([^<]*)</td><td>([^<]*)</td>"
        r"<td>([^<]*)</td><td>([^<]*)</td><td>([^<]*)</td><td>([^<]*)</td></tr>"
    )
    deals = []
    for m in pattern.finditer(html):
        profit_raw = m.group(11).replace(" ", "").replace("\xa0", "")
        try:
            profit = float(profit_raw)
        except ValueError:
            profit = 0.0
        deals.append(
            {
                "time": parse_mt5_dt(m.group(1)),
                "deal": int(m.group(2)),
                "symbol": m.group(3).strip(),
                "type": m.group(4).strip(),
                "direction": m.group(5).strip(),
                "volume": m.group(6).strip(),
                "price": m.group(7).strip(),
                "profit": profit,
                "comment": m.group(13).strip(),
            }
        )
    return deals


def build_positions(deals: list[dict]) -> list[dict]:
    open_pos = None
    positions = []
    for d in deals:
        if d["symbol"] != "XAUUSD" or d["direction"] not in ("in", "out"):
            continue
        if d["direction"] == "in":
            open_pos = {
                "open_time": d["time"],
                "open_deal": d["deal"],
                "side": "long" if d["type"] == "buy" else "short",
                "open_price": float(d["price"]) if d["price"] else 0,
                "open_comment": d["comment"],
            }
        elif open_pos:
            positions.append(
                {
                    **open_pos,
                    "close_time": d["time"],
                    "close_deal": d["deal"],
                    "close_price": float(d["price"]) if d["price"] else 0,
                    "profit": d["profit"],
                    "duration_min": int((d["time"] - open_pos["open_time"]).total_seconds() / 60),
                    "price_move": abs(
                        (float(d["price"]) if d["price"] else 0) - open_pos["open_price"]
                    ),
                }
            )
            open_pos = None
    return positions


def classify_loss(pos: dict) -> str:
    p = pos["profit"]
    if p <= -500:
        return "full_stop"
    if p <= STOP_LOSS_THRESHOLD:
        return "large_loss"
    return "small_loss"


def in_pause_window(t: datetime, start_h=22, end_h=6) -> bool:
    h = t.hour + t.minute / 60
    if start_h > end_h:
        return h >= start_h or h < end_h
    return start_h <= h < end_h


def nearest_news(exit_time: datetime, events: list[dict], window: int) -> list[dict]:
    hits = []
    for ev in events:
        delta = abs((exit_time - ev["datetime"]).total_seconds()) / 60
        if delta <= window:
            hits.append({**ev, "minutes_from_news": round(delta, 1)})
    return sorted(hits, key=lambda h: h["minutes_from_news"])


def categorize_stop(pos: dict, news: list[dict]) -> str:
    ct = pos["close_time"]
    ot = pos["open_time"]
    cls = classify_loss(pos)

    if ct.strftime("%H:%M:%S") == "19:00:00":
        return "session_close_19h"
    if nearest_news(ct, news, 45) or nearest_news(ct, news, 45):
        nh = nearest_news(ct, news, 45)
        if nh:
            return "news_release"
    if nearest_news(ct, news, 90):
        return "news_window_wide"
    if in_pause_window(ct) or in_pause_window(ot):
        return "overnight_pause_zone"
    if ot.hour < 8 and ct.hour >= 8 and pos["duration_min"] > 240:
        return "overnight_hold"
    if pos["duration_min"] <= 15 and cls == "full_stop":
        return "immediate_spike"
    if pos["duration_min"] >= 360 and cls == "full_stop":
        return "slow_bleed_to_sl"
    if 3 <= ot.hour < 8:
        return "early_morning"
    if 12 <= ot.hour < 15:
        return "london_ny_overlap_entry"
    return "intraday_other"


def main() -> None:
    html = read_html(REPORT)
    positions = build_positions(parse_deals(html))
    news = load_news_events()

    wins = [p for p in positions if p["profit"] >= 0]
    losses = [p for p in positions if p["profit"] < 0]
    full_stops = [p for p in losses if classify_loss(p) == "full_stop"]
    large = [p for p in losses if classify_loss(p) in ("full_stop", "large_loss")]

    # Category assignment (priority order)
    cat_map = {}
    for pos in large:
        cat = categorize_stop(pos, news)
        cat_map[pos["close_deal"]] = cat

    cat_stats = defaultdict(lambda: {"count": 0, "total_loss": 0.0, "examples": []})
    for pos in large:
        c = cat_map[pos["close_deal"]]
        cat_stats[c]["count"] += 1
        cat_stats[c]["total_loss"] += pos["profit"]
        if len(cat_stats[c]["examples"]) < 3:
            cat_stats[c]["examples"].append(
                {
                    "open": pos["open_time"].strftime("%Y-%m-%d %H:%M"),
                    "close": pos["close_time"].strftime("%Y-%m-%d %H:%M"),
                    "side": pos["side"],
                    "profit": pos["profit"],
                    "duration_min": pos["duration_min"],
                    "price_move": round(pos["price_move"], 2),
                }
            )

    # Hour of close for full stops
    close_hours = Counter(p["close_time"].hour for p in full_stops)
    open_hours = Counter(p["open_time"].hour for p in full_stops)

    # Side bias
    side_stats = {
        s: {"count": sum(1 for p in full_stops if p["side"] == s), "loss": sum(p["profit"] for p in full_stops if p["side"] == s)}
        for s in ("long", "short")
    }

    # Duration buckets
    dur_buckets = {"0-15m": 0, "16-60m": 0, "1-4h": 0, "4-8h": 0, "8h+": 0}
    dur_loss = defaultdict(float)
    for p in full_stops:
        d = p["duration_min"]
        if d <= 15:
            k = "0-15m"
        elif d <= 60:
            k = "16-60m"
        elif d <= 240:
            k = "1-4h"
        elif d <= 480:
            k = "4-8h"
        else:
            k = "8h+"
        dur_buckets[k] += 1
        dur_loss[k] += p["profit"]

    # Price move at SL (~55 points for 0.1 lot = $550)
    avg_move = sum(p["price_move"] for p in full_stops) / len(full_stops) if full_stops else 0

    # Consecutive stop days
    stop_dates = sorted({p["close_time"].date() for p in full_stops})

    # Same-day re-entry after stop
    reentry_same_day = 0
    for i, p in enumerate(full_stops):
        d = p["close_time"].date()
        later = [x for x in positions if x["open_time"].date() == d and x["open_time"] > p["close_time"] and x["profit"] < -100]
        if later:
            reentry_same_day += 1

    # Pause zone: 22:00-06:00
    pause_opens = sum(1 for p in full_stops if in_pause_window(p["open_time"]))
    pause_closes = sum(1 for p in full_stops if in_pause_window(p["close_time"]))

    result = {
        "summary": {
            "total_trades": len(positions),
            "wins": len(wins),
            "losses": len(losses),
            "full_stops": len(full_stops),
            "full_stop_loss_total": round(sum(p["profit"] for p in full_stops), 2),
            "avg_full_stop_loss": round(sum(p["profit"] for p in full_stops) / len(full_stops), 2) if full_stops else 0,
            "avg_win": round(sum(p["profit"] for p in wins) / len(wins), 2) if wins else 0,
            "avg_price_move_at_full_sl": round(avg_move, 2),
            "reentry_same_day_after_stop": reentry_same_day,
        },
        "by_category": {
            k: {"count": v["count"], "total_loss": round(v["total_loss"], 2), "examples": v["examples"]}
            for k, v in sorted(cat_stats.items(), key=lambda x: x[1]["total_loss"])
        },
        "close_hour_distribution": dict(close_hours.most_common()),
        "open_hour_distribution": dict(open_hours.most_common(10)),
        "side_stats": side_stats,
        "duration_buckets": {k: {"count": dur_buckets[k], "loss": round(dur_loss[k], 2)} for k in dur_buckets},
        "pause_zone_stops": {"opened_in_pause": pause_opens, "closed_in_pause": pause_closes},
    }

    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
