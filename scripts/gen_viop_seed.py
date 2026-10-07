"""One-off helper: build app/data/viop_contracts_seed.json from calc contracts.ts."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
text = (ROOT / "calc" / "src" / "lib" / "contracts.ts").read_text(encoding="utf-8")

pay = re.findall(
    r'\["([A-Z0-9]+)",\s*"([^"]+)",\s*([0-9.]+),\s*([0-9.]+),\s*([0-9.]+)\]',
    text,
)
objs = re.findall(
    r'\{\s*ticker:\s*"([^"]+)",\s*name:\s*"([^"]+)",\s*margin:\s*([0-9.]+),\s*'
    r'price:\s*([0-9.]+),\s*leverage:\s*([0-9.]+),\s*multiplier:\s*([0-9.]+),\s*'
    r'currency:\s*"([^"]+)",\s*group:\s*"([^"]+)"\s*\}',
    text,
)

seed: list[dict] = []
for t, n, m, p, l, mult, cur, g in objs:
    price = float(p)
    margin = float(m)
    multiplier = float(mult)
    rate = (margin / (price * multiplier) * 100) if price * multiplier else 0.0
    seed.append(
        {
            "ticker": t,
            "name": n,
            "margin": margin,
            "price": price,
            "leverage": float(l),
            "multiplier": multiplier,
            "currency": cur,
            "group": g,
            "margin_rate_pct": round(rate, 4),
        }
    )
for t, n, m, p, l in pay:
    price = float(p)
    margin = float(m)
    multiplier = 100.0
    rate = (margin / (price * multiplier) * 100) if price * multiplier else 0.0
    seed.append(
        {
            "ticker": t,
            "name": n,
            "margin": margin,
            "price": price,
            "leverage": float(l),
            "multiplier": multiplier,
            "currency": "TL",
            "group": "pay",
            "margin_rate_pct": round(rate, 4),
        }
    )

out = ROOT / "app" / "data" / "viop_contracts_seed.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(
    json.dumps({"contracts": seed}, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print(f"wrote {len(seed)} contracts -> {out}")
