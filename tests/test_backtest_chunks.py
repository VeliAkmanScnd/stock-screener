import pandas as pd

from app.services.borsapy_client import backtest_chunk_windows, merge_ohlcv_parts


def test_chunk_windows_cover_thirteen_months_of_15m():
    start = pd.Timestamp("2025-09-01")
    end = pd.Timestamp("2026-10-31")
    windows = backtest_chunk_windows(start, end, 140, overlap_days=3)
    assert len(windows) >= 3
    assert windows[0][1] == end
    assert windows[-1][0] == start
    for w_start, w_end in windows:
        assert w_end > w_start
        assert (w_end - w_start).days <= 140


def test_merge_ohlcv_parts_dedupes_overlap():
    a = pd.DataFrame(
        {"Open": [1, 2], "High": [1, 2], "Low": [1, 2], "Close": [1, 2], "Volume": [1, 1]},
        index=pd.to_datetime(["2026-01-01", "2026-01-02"]),
    )
    b = pd.DataFrame(
        {"Open": [2.5, 3], "High": [2.5, 3], "Low": [2.5, 3], "Close": [2.5, 3], "Volume": [1, 1]},
        index=pd.to_datetime(["2026-01-02", "2026-01-03"]),
    )
    out = merge_ohlcv_parts([a, b])
    assert list(out.index.strftime("%Y-%m-%d")) == ["2026-01-01", "2026-01-02", "2026-01-03"]
    assert float(out.loc[pd.Timestamp("2026-01-02"), "Close"]) == 2.5
