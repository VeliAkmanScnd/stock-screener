import numpy as np
import pandas as pd

from app.services.bias_optimizer import (
    build_grid,
    combo_passes,
    expand_combos,
    search_bias_params,
)
from app.services.pine_market_bias import market_bias_series, summarize_bias_trades


def _wave_frame(n: int = 480) -> pd.DataFrame:
    idx = pd.date_range("2026-01-02", periods=n, freq="15min")
    close = 100 + 8 * np.sin(np.arange(n) / 12.0)
    return pd.DataFrame(
        {
            "Open": close - 0.2,
            "High": close + 0.9,
            "Low": close - 0.9,
            "Close": close,
            "Volume": 1000.0,
        },
        index=idx,
    )


def test_summarize_win_rate_and_drawdown():
    trades = [
        {"side": "long", "pnl_pct": 10, "reason": "target"},
        {"side": "short", "pnl_pct": -5, "reason": "stop"},
        {"side": "long", "pnl_pct": 4, "reason": "reverse"},
    ]
    m = summarize_bias_trades(trades, start_equity=10000)
    assert m["trades"] == 3
    assert m["wins"] == 2
    assert m["win_rate"] == 66.67
    assert m["profit_factor"] > 1
    assert m["net_profit_pct"] > 0
    assert m["max_drawdown"] > 0


def test_wave_backtest_records_trades():
    df = _wave_frame()
    s = market_bias_series(
        df,
        ha_len=8,
        ha_len2=8,
        osc_len=3,
        require_bar=False,
        reverse_exit=True,
        allow_long=True,
        allow_short=True,
        exit_mode="Percent",
        tp_pct=2.0,
        sl_pct=1.0,
        max_same=8,
        chart_tf="15m",
    )
    assert "trades" in s
    metrics = summarize_bias_trades(s["trades"])
    assert metrics["trades"] >= 1
    assert 0 <= metrics["win_rate"] <= 100
    assert metrics["max_drawdown"] >= 0


def test_grid_expand_respects_cap():
    grid = build_grid(
        {
            "mode": "full",
            "ha_len": "40,52,64,76,88",
            "side": "both",
        }
    )
    combos = expand_combos(grid, max_combos=40, seed=1)
    assert len(combos) == 40
    assert all("ha_len" in c and "exit_mode" in c for c in combos)


def test_search_ranks_passing_rows_first():
    df = _wave_frame(360)
    combos = [
        {
            "ha_len": 8,
            "ha_len2": 8,
            "osc_len": 3,
            "ha_htf": "",
            "exit_mode": "Percent",
            "rr_mult": 1.0,
            "swing_bars": 4,
            "tp_pct": 2.0,
            "sl_pct": 1.0,
            "allow_long": True,
            "allow_short": True,
            "reverse_exit": True,
            "require_bar": False,
            "max_same": 8,
        },
        {
            "ha_len": 12,
            "ha_len2": 12,
            "osc_len": 5,
            "ha_htf": "",
            "exit_mode": "Percent",
            "rr_mult": 1.0,
            "swing_bars": 4,
            "tp_pct": 2.0,
            "sl_pct": 1.0,
            "allow_long": True,
            "allow_short": True,
            "reverse_exit": False,
            "require_bar": False,
            "max_same": 2,
        },
    ]
    found = search_bias_params(
        df,
        chart_tf="15m",
        combos=combos,
        filters={
            "min_win_rate": 0,
            "max_drawdown": 100,
            "min_profit_factor": 0,
            "min_profit": -100,
            "min_trades": 1,
        },
    )
    assert found["tested"] == 2
    assert found["results"]
    assert found["results"][0]["rank"] == 1
    assert "params" in found["results"][0]


def test_filters_reject_low_win_rate():
    metrics = {
        "trades": 20,
        "win_rate": 30,
        "max_drawdown": 5,
        "profit_factor": 1.5,
        "net_profit_pct": 12,
    }
    assert combo_passes(metrics, {
        "min_trades": 8,
        "min_win_rate": 45,
        "max_drawdown": 20,
        "min_profit_factor": 1.2,
        "min_profit": 5,
    }) is False
    metrics["win_rate"] = 50
    assert combo_passes(metrics, {
        "min_trades": 8,
        "min_win_rate": 45,
        "max_drawdown": 20,
        "min_profit_factor": 1.2,
        "min_profit": 5,
    }) is True
