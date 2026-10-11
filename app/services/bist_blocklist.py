"""Symbols to exclude from BIST universe (delisted / no Yahoo data)."""

from __future__ import annotations

import logging
from pathlib import Path

from app.config import BASE_DIR
from app.services.ticker_format import clean_bist_symbol

logger = logging.getLogger(__name__)

BLOCKLIST_PATH = BASE_DIR / "storage" / "bist_blocklist.txt"

# Delisted names. Yahoo and borsapy both return no bars, so they stay out of
# the calc ranking list and the BIST universe.
DEFAULT_BLOCKLIST: frozenset[str] = frozenset(
    {
        "ADANA",
        "ADBGR",
        "ADNAC",
        "AKFEN",
        "AKGUV",
        "AKSEL",
        "ALYAG",
        "ANACM",
        "ANELT",
        "ARBUL",
        "ARMDA",
        "ASLAN",
        "ATPET",
        "AVISA",
        "BISAS",
        "BMEKS",
        "BOLUC",
        "BOYNR",
        "BOYP",
        "COMDO",
        "DAGHL",
        "DENCM",
        "DENIZ",
        "DGKLB",
        "DGZTE",
        "EGCYH",
        "ENRYA",
        "FFKRL",
        "FINBN",
        "GMSTRF",
        "GRTRK",
        "GUSGR",
        "HZNDR",
        "IHMAD",
        "ISATR",
        "ITTFH",
        "IZOCM",
        "KILER",
        "KIPA",
        "KOMHL",
        "KOZAA",
        "KRATL",
        "LYDIA",
        "MIPAZ",
        "MRDIN",
        "NTTUR",
        "OLMIP",
        "OZBAL",
        "PEGYO",
        "PIMAS",
        "QNBFB",
        "QNBFL",
        "ROYAL",
        "SODA",
        "TEKST",
        "TETMT",
        "TIRE",
        "TRKCM",
        "UMPAS",
        "UNICO",
        "UNYEC",
        "USAS",
        "USDTRF",
        "UTPYA",
        "UYUM",
        "UZERB",
        "YAZIC",
        "YGYO",
        "ZGOLDF",
    }
)


def load_bist_blocklist() -> frozenset[str]:
    codes = set(DEFAULT_BLOCKLIST)
    if BLOCKLIST_PATH.is_file():
        for line in BLOCKLIST_PATH.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            code = clean_bist_symbol(line)
            if code:
                codes.add(code)
    return frozenset(codes)


def filter_bist_blocklist(symbols: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    block = load_bist_blocklist()
    if not block:
        return tuple(symbols)
    out = tuple(s for s in symbols if clean_bist_symbol(s) not in block)
    removed = len(symbols) - len(out)
    if removed:
        logger.info("BIST blocklist excluded %d symbol(s)", removed)
    return out
