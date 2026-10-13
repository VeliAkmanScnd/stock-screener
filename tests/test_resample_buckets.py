"""15m bars built from 5m must not use a mid-window close."""

import unittest
from datetime import datetime, timedelta

import pandas as pd

from app.services.batch_data import _resample_ohlcv
from app.services.ohlcv_store import merge_tail


def _bars(start: datetime, minutes: int, n: int, close_at: dict[int, float] | None = None) -> pd.DataFrame:
    close_at = close_at or {}
    idx = [start + timedelta(minutes=minutes * i) for i in range(n)]
    close = [close_at.get(i, 100.0) for i in range(n)]
    return pd.DataFrame(
        {
            "Open": close,
            "High": [c + 1 for c in close],
            "Low": [c - 1 for c in close],
            "Close": close,
            "Volume": [1.0] * n,
        },
        index=pd.DatetimeIndex(idx),
    )


class ResampleBucketTests(unittest.TestCase):
    def test_partial_15m_bucket_is_not_a_close(self):
        # 11 full 15m windows (09:00 through 11:30) plus 11:45 and 11:50 only.
        # The 11:45 window still needs the 11:55 bar. Its close must not be used.
        start = datetime(2026, 10, 13, 9, 0)
        frame = _bars(start, 5, 11 * 3 + 2, {11 * 3: 50.0, 11 * 3 + 1: 50.0})
        out = _resample_ohlcv(frame, "15min")
        self.assertIsNotNone(out)
        self.assertNotIn(pd.Timestamp("2026-10-13 11:45"), out.index)
        self.assertEqual(float(out.loc[pd.Timestamp("2026-10-13 11:30"), "Close"]), 100.0)

    def test_finished_15m_close_is_the_last_5m_close(self):
        # Middle 5m of the last window closes through 50; the last 5m closes back at 70.
        # The 15m candle is a wick. Its close is 70.
        start = datetime(2026, 10, 13, 9, 0)
        n = 11 * 3
        last = n - 3
        frame = _bars(start, 5, n, {last + 1: 50.0, last + 2: 70.0})
        out = _resample_ohlcv(frame, "15min")
        self.assertEqual(float(out.iloc[-1]["Close"]), 70.0)
        self.assertEqual(float(out.iloc[-1]["Low"]), 49.0)

    def test_live_5m_print_is_not_a_15m_close(self):
        # The closing 5m slot exists, but nothing has opened in the next window
        # and the clock is only 10s past the boundary. That close is still the
        # last trade (SKBNK 10:10 printed 5.25, then settled at 5.21).
        start = datetime(2026, 10, 13, 9, 0)
        n = 11 * 3
        frame = _bars(start, 5, n, {n - 1: 50.0})
        asof = pd.Timestamp("2026-10-13 11:45:10")
        out = _resample_ohlcv(frame, "15min", asof=asof)
        self.assertNotIn(pd.Timestamp("2026-10-13 11:30"), out.index)
        self.assertEqual(out.index[-1], pd.Timestamp("2026-10-13 11:15"))

    def test_settled_15m_close_is_kept_without_a_later_bar(self):
        start = datetime(2026, 10, 13, 9, 0)
        n = 11 * 3
        frame = _bars(start, 5, n, {n - 1: 70.0})
        asof = pd.Timestamp("2026-10-13 11:47")
        out = _resample_ohlcv(frame, "15min", asof=asof)
        self.assertEqual(out.index[-1], pd.Timestamp("2026-10-13 11:30"))
        self.assertEqual(float(out.iloc[-1]["Close"]), 70.0)

    def test_next_5m_bar_confirms_the_15m_close(self):
        start = datetime(2026, 10, 13, 9, 0)
        n = 11 * 3 + 1
        frame = _bars(start, 5, n, {n - 2: 70.0})
        asof = pd.Timestamp("2026-10-13 11:45:10")
        out = _resample_ohlcv(frame, "15min", asof=asof)
        self.assertEqual(float(out.loc[pd.Timestamp("2026-10-13 11:30"), "Close"]), 70.0)
        self.assertNotIn(pd.Timestamp("2026-10-13 11:45"), out.index)

    def test_revised_tail_replaces_a_partial_close(self):
        idx = pd.to_datetime(["2026-10-13 09:00", "2026-10-13 09:15", "2026-10-13 09:30"])
        old = pd.DataFrame(
            {"Open": [1, 1, 1], "High": [2, 2, 2], "Low": [0, 0, 0], "Close": [10, 10, 50], "Volume": [1, 1, 1]},
            index=idx,
        )
        new = old.iloc[:2].copy()
        new.loc[idx[1], "Close"] = 12
        merged = merge_tail(old, new)
        self.assertNotIn(pd.Timestamp("2026-10-13 09:30"), merged.index)
        self.assertEqual(float(merged.loc[idx[1], "Close"]), 12)

        fixed = old.copy()
        fixed.loc[idx[2], "Close"] = 70
        merged = merge_tail(old, fixed.iloc[1:])
        self.assertEqual(float(merged.loc[idx[2], "Close"]), 70)
        self.assertEqual(float(merged.loc[idx[0], "Close"]), 10)


class BarSettleTests(unittest.TestCase):
    def test_cache_saved_before_the_close_is_not_final(self):
        from datetime import timezone

        from app.services.ohlcv_store import fetched_after_bar_close

        idx = pd.DatetimeIndex([pd.Timestamp("2026-10-13 10:00")])
        frame = pd.DataFrame(
            {"Open": [1], "High": [2], "Low": [0], "Close": [5.25], "Volume": [1]},
            index=idx,
        )
        # 10:12 and 10:16 Istanbul.
        early = datetime(2026, 10, 13, 7, 12, tzinfo=timezone.utc)
        late = datetime(2026, 10, 13, 7, 16, tzinfo=timezone.utc)
        self.assertFalse(fetched_after_bar_close(frame, early, "15m"))
        self.assertTrue(fetched_after_bar_close(frame, late, "15m"))

    def test_settle_wait_is_only_just_after_the_boundary(self):
        from zoneinfo import ZoneInfo

        from app.services.bar_close import seconds_until_bar_settled

        ist = ZoneInfo("Europe/Istanbul")
        just_closed = datetime(2026, 10, 13, 10, 15, 5, tzinfo=ist)
        later = datetime(2026, 10, 13, 10, 16, tzinfo=ist)
        self.assertEqual(seconds_until_bar_settled("15m", just_closed), 40)
        self.assertEqual(seconds_until_bar_settled("15m", later), 0)

    def test_previous_bar_does_not_block_the_new_slot(self):
        from zoneinfo import ZoneInfo

        from app.services.schedule_runner import _started_before_current_slot

        ist = ZoneInfo("Europe/Istanbul")
        started = datetime(2026, 10, 13, 10, 0, tzinfo=ist)
        now = datetime(2026, 10, 13, 10, 16, tzinfo=ist)
        same = datetime(2026, 10, 13, 10, 15, 20, tzinfo=ist)
        self.assertTrue(_started_before_current_slot("15m", started, now))
        self.assertFalse(_started_before_current_slot("15m", same, now))


if __name__ == "__main__":
    unittest.main()
