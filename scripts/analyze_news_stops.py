"""Cross-reference MT5 strategy tester deals with news calendar."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

REPORT = Path(r"C:\Users\Dell\Downloads\aralık-haziran-6596-usd.html")
NEWS_DIR = Path(__file__).resolve().parents[1] / "storage" / "news_calendar"
OUT = Path(__file__).resolve().parents[1] / "storage" / "strategy_tester" / "news_stop_analysis.json"

# MT5 server time for IC Markets ≈ EET/EEST; calendar times look like Istanbul/local FF export.
# Match window: exit within ±minutes of scheduled news release.
NEWS_MATCH_MINUTES = 45
STOP_LOSS_THRESHOLD = -100  # USD; EA StopLoss_Dollar=550


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
    hour = int(m.group(1))
    minute = int(m.group(2))
    if m.group(3) == "pm" and hour != 12:
        hour += 12
    if m.group(3) == "am" and hour == 12:
        hour = 0
    d = datetime.strptime(date_str, "%Y-%m-%d")
    return d.replace(hour=hour, minute=minute)


def load_news_events() -> list[dict]:
    events: list[dict] = []
    for path in sorted(NEWS_DIR.glob("2026-*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for ev in data.get("events", []):
            dt = parse_news_time(ev["date"], ev.get("time") or "")
            if dt is None:
                continue
            events.append(
                {
                    "datetime": dt,
                    "date": ev["date"],
                    "time": ev.get("time"),
                    "currency": ev.get("currency"),
                    "event": ev.get("event"),
                    "actual": ev.get("actual"),
                }
            )
    events.sort(key=lambda e: e["datetime"])
    return events


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
    """Pair in/out deals into closed positions."""
    open_pos: dict | None = None
    positions: list[dict] = []
    for d in deals:
        if d["symbol"] != "XAUUSD" or d["direction"] not in ("in", "out"):
            continue
        if d["direction"] == "in":
            side = "long" if d["type"] == "buy" else "short"
            open_pos = {
                "open_time": d["time"],
                "open_deal": d["deal"],
                "side": side,
                "open_price": d["price"],
                "open_comment": d["comment"],
            }
        elif open_pos is not None:
            positions.append(
                {
                    **open_pos,
                    "close_time": d["time"],
                    "close_deal": d["deal"],
                    "close_price": d["price"],
                    "profit": d["profit"],
                    "duration_min": int((d["time"] - open_pos["open_time"]).total_seconds() / 60),
                }
            )
            open_pos = None
    return positions


def classify_exit(pos: dict) -> str:
    p = pos["profit"]
    if p <= -500:
        return "stop_loss"
    if p <= STOP_LOSS_THRESHOLD:
        return "large_loss"
    if p < 0:
        return "small_loss"
    return "win"


def nearest_news(exit_time: datetime, events: list[dict], window: int) -> list[dict]:
    hits = []
    for ev in events:
        delta = abs((exit_time - ev["datetime"]).total_seconds()) / 60
        if delta <= window:
            hits.append({**ev, "minutes_from_news": round(delta, 1)})
    hits.sort(key=lambda h: h["minutes_from_news"])
    return hits


def main() -> None:
    html = read_html(REPORT)
    deals = parse_deals(html)
    positions = build_positions(deals)
    news = load_news_events()

    losing = [p for p in positions if p["profit"] < 0]
    stopped = [p for p in positions if classify_exit(p) in ("stop_loss", "large_loss")]

    news_correlated: list[dict] = []
    for pos in stopped:
        hits = nearest_news(pos["close_time"], news, NEWS_MATCH_MINUTES)
        if not hits:
            continue
        news_correlated.append(
            {
                **pos,
                "exit_class": classify_exit(pos),
                "open_time": pos["open_time"].strftime("%Y-%m-%d %H:%M:%S"),
                "close_time": pos["close_time"].strftime("%Y-%m-%d %H:%M:%S"),
                "matched_news": hits[:3],
                "best_match_minutes": hits[0]["minutes_from_news"],
                "best_match_event": hits[0]["event"],
            }
        )

    # Also check all 116 losses for any news proximity
    all_loss_news = []
    for pos in losing:
        hits = nearest_news(pos["close_time"], news, NEWS_MATCH_MINUTES)
        if hits:
            all_loss_news.append(
                {
                    "close_time": pos["close_time"].strftime("%Y-%m-%d %H:%M:%S"),
                    "profit": pos["profit"],
                    "side": pos["side"],
                    "exit_class": classify_exit(pos),
                    "event": hits[0]["event"],
                    "news_time": hits[0]["datetime"].strftime("%Y-%m-%d %H:%M"),
                    "minutes_from_news": hits[0]["minutes_from_news"],
                }
            )

    summary = {
        "report": str(REPORT),
        "period": "2025.12.01 - 2026.06.23",
        "settings": {
            "stop_loss_usd": 550,
            "enable_news_filter": False,
            "news_match_window_minutes": NEWS_MATCH_MINUTES,
        },
        "total_positions": len(positions),
        "losing_positions": len(losing),
        "stop_or_large_loss": len(stopped),
        "news_correlated_stops": len(news_correlated),
        "all_losses_near_news": len(all_loss_news),
        "total_loss_from_news_stops": round(sum(p["profit"] for p in news_correlated), 2),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "summary": summary,
                "news_correlated_stops": sorted(
                    news_correlated, key=lambda x: x["close_time"]
                ),
                "all_losses_near_news": sorted(
                    all_loss_news, key=lambda x: x["close_time"]
                ),
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2))
    print("\n--- News-correlated stop/large losses ---")
    for row in sorted(news_correlated, key=lambda x: x["profit"]):
        print(
            f"{row['close_time']}  {row['profit']:>8.2f}  {row['side']:>5}  "
            f"{row['best_match_minutes']:>4.0f}m before/after  {row['best_match_event']}"
        )


def extended_stats() -> None:
    html = read_html(REPORT)
    positions = build_positions(parse_deals(html))
    news = load_news_events()
    stopped = [p for p in positions if classify_exit(p) in ("stop_loss", "large_loss")]
    analysis = json.loads(OUT.read_text(encoding="utf-8"))
    matched = {x["close_deal"] for x in analysis["news_correlated_stops"]}
    unmatched = [p for p in stopped if p["close_deal"] not in matched]

    print(f"Unmatched stop/large losses: {len(unmatched)}")
    print(f"Unmatched total loss: {sum(p['profit'] for p in unmatched):.2f}")
    wide = []
    for p in stopped:
        hits = nearest_news(p["close_time"], news, 90)
        if hits:
            wide.append((p, hits[0]))
    print(f"\nAll stops within 90 min of news ({len(wide)}):")
    for p, ev in sorted(wide, key=lambda x: x[0]["close_time"]):
        diff = (p["close_time"] - ev["datetime"]).total_seconds() / 60
        print(
            f"  {p['close_time']}  {p['profit']:8.1f}  {p['side']:5}  "
            f"{ev['event'][:42]:42}  news {ev['datetime'].strftime('%H:%M')}  diff {diff:+.0f}m"
        )

    pause_closes = [p for p in positions if p["profit"] < 0 and p["close_time"].strftime("%H:%M:%S") == "19:00:00"]
    print(f"\n19:00:00 partial/full closes (likely session rule): {len(pause_closes)}")
    print(f"  Total loss at 19:00: {sum(p['profit'] for p in pause_closes):.2f}")

    dec_stops = [p for p in stopped if p["close_time"].year == 2025]
    print(f"\nDec 2025 stop losses (no news calendar): {len(dec_stops)}, loss {sum(p['profit'] for p in dec_stops):.2f}")

    keywords = ["Non-Farm", "NFP", "FOMC", "CPI", "PCE", "GDP", "Employment", "Rate", "PMI", "Retail", "Claims"]
    print("\nUnmatched on high-impact news days (same day, any time):")
    for p in sorted(unmatched, key=lambda x: x["profit"]):
        d = p["close_time"].strftime("%Y-%m-%d")
        evs = [
            ev
            for ev in news
            if ev["date"] == d and any(k.lower() in ev["event"].lower() for k in keywords)
        ]
        if not evs:
            continue
        ev = min(evs, key=lambda e: abs((p["close_time"] - e["datetime"]).total_seconds()))
        diff = (p["close_time"] - ev["datetime"]).total_seconds() / 60
        print(
            f"  {p['close_time']}  {p['profit']:8.1f}  {p['side']:5}  "
            f"{ev['event'][:42]:42}  news {ev['datetime'].strftime('%H:%M')}  diff {diff:+.0f}m"
        )


if __name__ == "__main__":
    main()
    print()
    extended_stats()
