"""Alarm catch-up: a bar a run missed is scored by the next run, and bars from a
previous session (stale) are never sent."""

import pandas as pd

from app.services.bar_close import (
    ALARM_MAX_BAR_AGE_BARS,
    bar_close_age_seconds,
    timeframe_seconds,
)
from app.services.screener import alarm_candidate_bars


def _index(n: int = 10) -> pd.DatetimeIndex:
    return pd.date_range("2026-11-16 09:30", periods=n, freq="15min")


def test_first_sight_scores_only_last_closed_bar():
    idx = _index()
    assert alarm_candidate_bars(idx, None, 4) == [idx[-1]]


def test_no_new_bar_means_no_candidates():
    idx = _index()
    assert alarm_candidate_bars(idx, str(idx[-1]), 4) == []


def test_missed_bar_is_picked_up_by_next_run():
    """Run A saw bar 5. Run B sees bar 7 but bar 6 was never scored by run A."""
    idx = _index()
    got = alarm_candidate_bars(idx[:8], str(idx[5]), 4)
    assert got == [idx[6], idx[7]]


def test_candidates_are_capped_to_recent_bars():
    idx = _index(30)
    got = alarm_candidate_bars(idx, str(idx[2]), ALARM_MAX_BAR_AGE_BARS)
    assert got == list(idx[-ALARM_MAX_BAR_AGE_BARS:])


def test_tz_mismatch_between_mark_and_index_is_handled():
    idx = _index().tz_localize("Europe/Istanbul")
    got = alarm_candidate_bars(idx, "2026-11-16T09:30:00", 4)
    assert got == list(idx[-4:])


def test_bar_close_age_monday_first_bar_and_friday_bar():
    # Monday 09:30 bar closes 09:45; scanned 09:46 -> about one minute old.
    age = bar_close_age_seconds(
        "2026-11-16 09:30:00", "15m", universe="viop", now=pd.Timestamp("2026-11-16 09:46:00")
    )
    assert age is not None and abs(age - 60) < 1

    # Friday 17:45 bar seen on Monday 09:46 -> far beyond the limit.
    friday_age = bar_close_age_seconds(
        "2026-11-13 17:45:00", "15m", universe="viop", now=pd.Timestamp("2026-11-16 09:46:00")
    )
    limit = ALARM_MAX_BAR_AGE_BARS * timeframe_seconds("15m")
    assert friday_age > limit
    assert age <= limit
