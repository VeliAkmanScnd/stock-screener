"""FX universe: majors plus gold and silver, 3m built from 1m."""

import unittest
from datetime import datetime, timedelta

import pandas as pd

from app.services.batch_data import _resample_ohlcv
from app.services.data_fetcher import get_fx_symbols, parse_symbol_list
from app.services.fx_data import FX_PAIRS, _istanbul_naive, display_symbol, yf_symbol
from app.services.telegram_service import format_signal_telegram_card
from app.services.ticker_format import clean_fx_symbol, to_yf_ticker
from app.services.tv_export import to_tradingview_symbol


class FxUniverseTests(unittest.TestCase):
    def test_nine_pairs(self):
        self.assertEqual(len(FX_PAIRS), 9)
        self.assertEqual(get_fx_symbols(), FX_PAIRS)
        self.assertIn("EURUSD", FX_PAIRS)
        self.assertIn("XAUUSD", FX_PAIRS)
        self.assertIn("XAGUSD", FX_PAIRS)

    def test_yahoo_symbols(self):
        self.assertEqual(yf_symbol("EURUSD"), "EURUSD=X")
        self.assertEqual(yf_symbol("USDJPY"), "USDJPY=X")
        self.assertEqual(to_yf_ticker("XAUUSD", "fx"), "GC=F")
        self.assertEqual(to_yf_ticker("XAGUSD", "fx"), "SI=F")
        self.assertEqual(display_symbol("GC=F"), "XAUUSD")
        self.assertEqual(display_symbol("SI=F"), "XAGUSD")

    def test_aliases(self):
        self.assertEqual(clean_fx_symbol("XAU"), "XAUUSD")
        self.assertEqual(clean_fx_symbol("gold"), "XAUUSD")
        self.assertEqual(clean_fx_symbol("XAG"), "XAGUSD")
        self.assertEqual(clean_fx_symbol("FX:EURUSD"), "EURUSD")
        parsed = parse_symbol_list("eurusd, XAU, SILVER, AAPL", "fx")
        self.assertEqual(parsed, ["EURUSD", "XAGUSD", "XAUUSD"])

    def test_istanbul_from_utc(self):
        idx = pd.DatetimeIndex([datetime(2026, 10, 13, 10, 0)], tz="UTC")
        frame = pd.DataFrame(
            {"Open": [1.1], "High": [1.2], "Low": [1.0], "Close": [1.11], "Volume": [0.0]},
            index=idx,
        )
        out = _istanbul_naive(frame)
        self.assertIsNone(out.index.tz)
        self.assertEqual(out.index[0], pd.Timestamp("2026-10-13 13:00"))

    def test_three_minute_resample(self):
        start = datetime(2026, 10, 13, 10, 0)
        # 10:00 through 10:35: twelve 3m windows, last one still open until 10:36.
        n = 36
        idx = [start + timedelta(minutes=i) for i in range(n)]
        close = [float(i) for i in range(n)]
        frame = pd.DataFrame(
            {
                "Open": close,
                "High": [c + 0.1 for c in close],
                "Low": [c - 0.1 for c in close],
                "Close": close,
                "Volume": [1.0] * n,
            },
            index=pd.DatetimeIndex(idx),
        )
        early = _resample_ohlcv(frame, "3min", asof=pd.Timestamp("2026-10-13 10:35", tz="Europe/Istanbul"))
        self.assertIsNotNone(early)
        self.assertEqual(early.index[-1], pd.Timestamp("2026-10-13 10:30"))
        self.assertEqual(float(early["Close"].iloc[-1]), 32.0)
        settled = _resample_ohlcv(
            frame, "3min", asof=pd.Timestamp("2026-10-13 10:36:50", tz="Europe/Istanbul")
        )
        self.assertEqual(settled.index[-1], pd.Timestamp("2026-10-13 10:33"))
        self.assertEqual(float(settled["Close"].iloc[-1]), 35.0)
        self.assertEqual(float(settled["Open"].iloc[0]), 0.0)
        self.assertAlmostEqual(float(settled["High"].iloc[0]), 2.1)

    def test_card_and_tv(self):
        card = format_signal_telegram_card(
            "EURUSD",
            1.11894,
            "AL",
            market="fx",
            exchange="FX",
            timeframe="3m",
        )
        self.assertIn("Kontrat\t: EURUSD", card)
        self.assertIn("1,11894", card)
        self.assertIn("3 dakika", card)
        gold = format_signal_telegram_card("XAUUSD", 4206.5, "AL", market="fx")
        self.assertIn("4206,50", gold)
        self.assertEqual(to_tradingview_symbol("XAUUSD", "fx"), "FX:XAUUSD")
        self.assertEqual(to_tradingview_symbol("eurusd", "fx"), "FX:EURUSD")


if __name__ == "__main__":
    unittest.main()
