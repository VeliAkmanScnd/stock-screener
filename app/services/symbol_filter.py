"""Filter exchange symbol directories to active common stocks only."""

from __future__ import annotations

import re
from typing import Any

# Security names that are usually not common equity
_JUNK_NAME_RES = [
    re.compile(p, re.I)
    for p in (
        r"\bwarrants?\b",
        r"\bunits?\b",
        r"\bpreferred\b",
        r"\bpreference\b",
        r"\bdebentures?\b",
        r"\bnotes due\b",
        r"\bbonds?\b",
        r"\btrust\b",
        r"\bclosed[- ]end\b",
        r"\betf\b",
        r"\bmutual fund\b",
        r"\bexchange[- ]traded\b",
        r"\bacquisition corp\b",
        r"\bspac\b",
        r"\bdepositary shares\b",
        r"\bright(s)?\b",
        r"\bl\.?\s*p\.?\b",
        r"\blimited partnership\b",
        r"\btreasury\b",
        r"\bconvertible\b",
    )
]

# Symbol patterns: warrants, units, rights, preferred classes
_SYMBOL_JUNK_RES = [
    re.compile(r"^.{1,4}-[WUR](?:T|S|N)?$", re.I),
    re.compile(r"^[A-Z]{4,5}[WU]$"),  # e.g. AAPLW, TSLAU
    re.compile(r"^[A-Z]{1,4}-P[A-Z]?$", re.I),  # preferred series
    re.compile(r"\$|/|\\"),  # preferred / when-class tickers
]

# Words in name that look like "unit" but aren't (Community, Opportunity)
_NAME_SAFE_EXCEPTIONS = ("community", "opportunity", "unity")


def is_junk_security_name(name: str) -> bool:
    if not name or not str(name).strip():
        return False
    low = str(name).lower()
    for rx in _JUNK_NAME_RES:
        if rx.search(low):
            if rx.pattern == r"\bunits?\b":
                if any(ex in low for ex in _NAME_SAFE_EXCEPTIONS):
                    continue
            return True
    return False


def is_tradeable_common_symbol(symbol: str) -> bool:
    """Exclude warrants, units, preferred tickers, malformed symbols."""
    if not symbol:
        return False
    s = symbol.strip().upper()
    if len(s) < 1 or len(s) > 6:
        return False
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]*", s):
        return False
    for rx in _SYMBOL_JUNK_RES:
        if rx.search(s):
            return False
    return True


def nasdaq_listed_row_passes(row: dict[str, Any]) -> bool:
    if (row.get("Test Issue") or "N").strip().upper() == "Y":
        return False
    if (row.get("ETF") or "N").strip().upper() == "Y":
        return False
    if (row.get("NextShares") or "N").strip().upper() == "Y":
        return False
    # N = normal; D/E/H/Q = deficient, delinquent, halted, bankrupt
    fs = (row.get("Financial Status") or "N").strip().upper()
    if fs and fs != "N":
        return False
    raw = row.get("Symbol") or ""
    sym = str(raw).strip().upper().replace(".", "-")
    if not is_tradeable_common_symbol(sym):
        return False
    if is_junk_security_name(str(row.get("Security Name") or "")):
        return False
    return True


def nyse_otherlisted_row_passes(row: dict[str, Any]) -> bool:
    ex = (row.get("Exchange") or "").strip().upper()
    if ex != "N":
        return False
    if (row.get("Test Issue") or "N").strip().upper() == "Y":
        return False
    if (row.get("ETF") or "N").strip().upper() == "Y":
        return False
    raw = row.get("ACT Symbol") or row.get("Symbol") or ""
    sym = str(raw).strip().upper().replace(".", "-")
    if not is_tradeable_common_symbol(sym):
        return False
    if is_junk_security_name(str(row.get("Security Name") or "")):
        return False
    return True
