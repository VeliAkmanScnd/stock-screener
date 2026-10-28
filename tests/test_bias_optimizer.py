import numpy as np
import pandas as pd

from app.services.bias_optimizer import (
    build_grid,
    combo_passes,
    expand_combos,
    numeric_span,
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


def test_htf_30_on_15m_does_not_hit_readonly_flags():
    df = _wave_frame(240)
    raw = df["Close"].to_numpy()
    raw.flags.writeable = False
    s = market_bias_series(
        df,
        ha_len=8,
        ha_len2=8,
        osc_len=3,
        ha_htf="30",
        chart_tf="15m",
        require_bar=False,
        reverse_exit=True,
        allow_long=True,
        allow_short=True,
        exit_mode="Swing RR",
        rr_mult=1.0,
        swing_bars=4,
        max_same=2,
    )
    assert len(s["long_go"]) == len(df)
    found = search_bias_params(
        df,
        chart_tf="15m",
        combos=[
            {
                "ha_len": 8,
                "ha_len2": 8,
                "osc_len": 3,
                "ha_htf": "30",
                "exit_mode": "Swing RR",
                "rr_mult": 1.0,
                "swing_bars": 4,
                "tp_pct": 2.0,
                "sl_pct": 1.0,
                "allow_long": True,
                "allow_short": True,
                "reverse_exit": True,
                "require_bar": False,
                "max_same": 2,
            }
        ],
        filters={
            "min_win_rate": 0,
            "max_drawdown": 100,
            "min_profit_factor": 0,
            "min_profit": -100,
            "min_trades": 1,
        },
    )
    assert found["tested"] == 1
    assert found["errors"] == 0
    assert found["results"]


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


def test_numeric_span_inclusive():
    vals = numeric_span(55, 200, 1, integer=True)
    assert vals[0] == 55
    assert vals[-1] == 200
    assert len(vals) == 146
    assert numeric_span(1.2, 2.0, 0.4, integer=False) == [1.2, 1.6, 2.0]


def test_disabled_axis_pins_to_start():
    grid = build_grid(
        {
            "mode": "quick",
            "ha_len": {"start": 48, "stop": 80, "step": 16},
            "ha_len2": {"start": 55, "stop": 60, "step": 1},
            "exit_mode": "Swing RR, Percent",
            "optimize": {
                "ha_len": False,
                "ha_len2": True,
                "exit_mode": False,
            },
        }
    )
    assert grid["ha_len"] == [48]
    assert grid["ha_len2"] == [55, 56, 57, 58, 59, 60]
    assert grid["exit_mode"] == ["Swing RR"]


def test_build_grid_from_start_step_stop():
    grid = build_grid(
        {
            "mode": "quick",
            "ha_len2": {"start": 55, "stop": 60, "step": 1},
            "exit_mode": "Swing RR",
        }
    )
    assert grid["ha_len2"] == [55, 56, 57, 58, 59, 60]


def test_percent_grid_uses_tp_sl_lists():
    grid = build_grid(
        {
            "mode": "quick",
            "exit_mode": "Percent",
            "tp_pct": {"start": 1.5, "stop": 2.5, "step": 1},
            "sl_pct": {"start": 1.0, "stop": 1.5, "step": 0.5},
            "rr_mult": {"start": 1.2, "stop": 2.0, "step": 0.4},
            "swing_bars": {"start": 8, "stop": 11, "step": 3},
            "ha_len": {"start": 64, "stop": 64, "step": 1},
            "ha_len2": {"start": 72, "stop": 72, "step": 1},
            "osc_len": {"start": 7, "stop": 7, "step": 1},
            "ha_htf": {"start": 30, "stop": 30, "step": 15},
            "max_same": {"start": 1, "stop": 1, "step": 1},
            "reverse_exit": "true",
            "require_bar": "false",
        }
    )
    assert grid["exit_mode"] == ["Percent"]
    assert grid["tp_pct"] == [1.5, 2.5]
    assert grid["sl_pct"] == [1.0, 1.5]
    assert len(grid["rr_mult"]) == 1
    assert len(grid["swing_bars"]) == 1
    combos = expand_combos(grid, max_combos=80, seed=1)
    assert combos
    assert all(c["exit_mode"] == "Percent" for c in combos)
    tps = {c["tp_pct"] for c in combos}
    sls = {c["sl_pct"] for c in combos}
    assert tps == {1.5, 2.5}
    assert sls == {1.0, 1.5}


def test_capped_grid_keeps_start_and_classic():
    grid = build_grid(
        {
            "mode": "quick",
            "ha_len": {"start": 48, "stop": 200, "step": 1},
            "ha_len2": {"start": 55, "stop": 200, "step": 1},
            "osc_len": {"start": 5, "stop": 20, "step": 1},
            "rr_mult": {"start": 1, "stop": 2, "step": 0.1},
            "swing_bars": {"start": 4, "stop": 30, "step": 1},
            "max_same": {"start": 1, "stop": 6, "step": 1},
            "ha_htf": {"start": 30, "stop": 30, "step": 15},
            "exit_mode": "Swing RR",
            "reverse_exit": "true, false",
            "require_bar": "false",
            "optimize": {"exit_mode": False, "require_bar": False, "ha_htf": False},
        }
    )
    combos = expand_combos(grid, max_combos=180, seed=1)
    assert len(combos) == 180
    assert any(c["ha_len"] == 48 and c["ha_len2"] == 55 and c["osc_len"] == 5 for c in combos)
    assert any(c["ha_len"] == 100 and c["ha_len2"] == 100 and c["osc_len"] == 7 for c in combos)


def test_search_raises_when_every_combo_fails():
    df = _wave_frame(120)
    combos = [
        {
            "ha_len": None,
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
        }
    ]
    try:
        search_bias_params(
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
    except RuntimeError as exc:
        assert "hesaplanamadı" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


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
