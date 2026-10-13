"""Signal entry is the 0.5 fib; take-profit is 1.7R from the strong stop."""

import unittest

from app.services.pine_strong_fresh import signal_trade_levels
from app.services.telegram_service import format_signal_telegram_card
from app.services.track_service import levels_from_signal


class SignalLevelTests(unittest.TestCase):
    def test_long_entry_is_midpoint_and_target_is_one_point_seven_r(self):
        # AKBNK chart: strong low 69.27, weak high 69.76, giriş 0.5 ≈ 69.52
        levels = signal_trade_levels(
            buy=True,
            strong_low=69.27,
            strong_high=None,
            weak_high=69.76,
            weak_low=None,
        )
        self.assertAlmostEqual(levels["fib_entry"], 69.515, places=6)
        self.assertAlmostEqual(levels["fib_stop"], 69.27, places=6)
        self.assertAlmostEqual(levels["fib_target"], 69.515 + 1.7 * (69.515 - 69.27), places=6)

    def test_short_target_is_below_entry(self):
        levels = signal_trade_levels(
            buy=False,
            strong_low=None,
            strong_high=100.0,
            weak_high=None,
            weak_low=90.0,
        )
        self.assertAlmostEqual(levels["fib_entry"], 95.0, places=6)
        self.assertAlmostEqual(levels["fib_target"], 86.5, places=6)
        self.assertAlmostEqual(levels["fib_stop"], 100.0, places=6)

    def test_card_uses_fib_entry_and_rr_target(self):
        levels = signal_trade_levels(
            buy=True,
            strong_low=69.27,
            strong_high=None,
            weak_high=69.76,
            weak_low=None,
        )
        card = format_signal_telegram_card(
            "AKBNK1!",
            69.46,
            "AL",
            market="viop",
            signals=levels,
        )
        self.assertIn("Fiyat\t: 69,46", card)
        self.assertIn("Giriş\t: 69,52", card)
        self.assertIn("Kar AL\t: 69,93", card)
        self.assertIn("Stop\t\t: 69,27", card)

    def test_card_without_fib_keeps_percent_targets(self):
        card = format_signal_telegram_card("AKBNK1!", 100.0, "AL", market="viop")
        self.assertNotIn("Giriş", card)
        self.assertIn("Kar AL\t: 104,00", card)
        self.assertIn("Stop\t\t: 97,00", card)

    def test_track_levels_follow_the_signal(self):
        levels = signal_trade_levels(
            buy=True,
            strong_low=69.27,
            strong_high=None,
            weak_high=69.76,
            weak_low=None,
        )
        planned = levels_from_signal(levels, "AL")
        self.assertIsNotNone(planned)
        entry, target, stop, target_pct, stop_pct = planned
        self.assertAlmostEqual(entry, 69.515, places=6)
        self.assertAlmostEqual(target, levels["fib_target"], places=6)
        self.assertAlmostEqual(stop, 69.27, places=6)
        self.assertAlmostEqual((target - entry) / (entry - stop), 1.7, places=6)
        self.assertGreater(target_pct, 0)
        self.assertGreater(stop_pct, 0)


class PerformanceBenchmarkTests(unittest.TestCase):
    def test_timeframe_target_is_one_point_seven_r(self):
        from app.services.track_levels import TARGET_R, level_benchmarks_for_api, reward_r

        for row in level_benchmarks_for_api():
            self.assertEqual(row["r_multiple"], TARGET_R)
            self.assertAlmostEqual(row["target_pct"], round(row["stop_pct"] * TARGET_R, 2), places=6)
        # 15m stop 1.5% and a +3.4% favorable extreme is 2.267R
        self.assertAlmostEqual(reward_r(3.4, 1.5), round(3.4 / 1.5, 3), places=6)
        self.assertIsNone(reward_r(3.4, 0))


if __name__ == "__main__":
    unittest.main()
