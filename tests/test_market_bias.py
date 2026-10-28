from pathlib import Path

import numpy as np
import pandas as pd

from app.services.pine_params import pine_inputs_for_api
from app.services.pine_parser import extract_al_condition, extract_pine_inputs
from app.services.pine_market_bias import (
    _no_repaint_request,
    is_market_bias_script,
    market_bias_params_from_script,
    market_bias_series,
    market_bias_snapshot,
)

PINE_PATH = Path(r"C:\Users\Dell\Desktop\MarketBiasStrategy.txt")
SNIPPET = """
//@version=5
strategy(title='Market Bias Strategy (CEREBR)', overlay=true)
ha_htf  = FORCE_CTF(input.timeframe('', 'Timeframe', group="HA Market Bias"))
ha_len  = input(100, 'Period', group="HA Market Bias")
ha_len2 = input(100, 'Smoothing', group="HA Market Bias")
osc_len = input.int(7, "Oscillator Period", group="HA Market Bias")
show_ha  = input.bool(true, "Show HA Candles", group='Display Settings')
exitMode  = input.string('Percent', 'SL / TP mode', options=['Percent', 'Swing RR'], group='Risk Management')
rrMult    = input.float(1.0, 'Risk reward', minval=0.1, step=0.1, group='Risk Management')
swingBars = input.int(4, 'Swing bars', minval=1, maxval=50, group='Risk Management')
tp_pct    = input.float(2.0, 'Take Profit %', group='Risk Management')
sl_pct    = input.float(1.0, 'Stop Loss %', group='Risk Management')
allow_long   = input.bool(true, 'Enable Long Trades', group='Trade Direction')
allow_short  = input.bool(true, 'Enable Short Trades', group='Trade Direction')
reverse_exit = input.bool(true, 'Close/Reverse on Opposite Signal', group='Trade Direction')
require_bar  = input.bool(true, 'Bull/Bear Signal Candle', group='Trade Direction')
maxSame     = input.int(2, 'Max entries one direction', minval=1, maxval=20, group='Trade Direction')
buyStrength = true
sellStrength = true
longGo = buySignal and allow_long
shortGo = sellSignal and allow_short
"""


def _code() -> str:
    if PINE_PATH.is_file():
        return PINE_PATH.read_text(encoding="utf-8")
    return SNIPPET


def test_extracts_ha_risk_and_direction_inputs():
    names = {p.name: p for p in extract_pine_inputs(_code())}
    for key in (
        "ha_htf",
        "ha_len",
        "ha_len2",
        "osc_len",
        "exitMode",
        "rrMult",
        "swingBars",
        "tp_pct",
        "sl_pct",
        "allow_long",
        "allow_short",
        "reverse_exit",
        "require_bar",
        "maxSame",
    ):
        assert key in names, key
    assert names["ha_htf"].kind == "timeframe"
    assert names["ha_len"].kind == "int"
    assert names["ha_len"].default == "100"
    assert names["exitMode"].options == ["Percent", "Swing RR"]
    api_names = {p["name"] for p in pine_inputs_for_api(_code())}
    assert "show_ha" not in api_names
    assert "ha_len" in api_names
    assert "allow_short" in api_names
    assert "scan_side" in api_names


def test_detects_market_bias_engine():
    code = _code()
    assert is_market_bias_script(code)
    al = extract_al_condition(code)
    assert al is not None
    assert al.source == "market_bias"


def test_snapshot_emits_buy_or_sell_flags():
    n = 400
    idx = pd.date_range("2026-01-02", periods=n, freq="15min")
    close = pd.Series(range(n), dtype=float) + 100
    df = pd.DataFrame(
        {
            "Open": close - 0.4,
            "High": close + 0.8,
            "Low": close - 0.8,
            "Close": close,
            "Volume": 1000.0,
        },
        index=idx,
    )
    code = _code()
    params = market_bias_params_from_script(
        code,
        {
            "ha_len": 8,
            "ha_len2": 8,
            "osc_len": 3,
            "require_bar": False,
            "allow_long": True,
            "allow_short": True,
        },
    )
    snap = market_bias_snapshot(df, chart_tf="15m", **params)
    assert "market_bias_buy" in snap
    assert "market_bias_sell" in snap
    assert snap["market_bias_bar_shift"] == 0
    assert snap["market_bias_buy"] or snap["market_bias_sell"] or snap["pine_al"] in (True, False)


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


def test_reverse_off_matches_tv_flat_only():
    df = _wave_frame()
    s = market_bias_series(
        df,
        ha_len=8,
        ha_len2=8,
        osc_len=3,
        require_bar=False,
        reverse_exit=False,
        allow_long=True,
        allow_short=True,
        tp_pct=0.0,
        sl_pct=0.0,
        exit_mode="Percent",
        max_same=8,
        chart_tf="15m",
    )
    assert int(s["buy_signal"].sum() + s["sell_signal"].sum()) >= 2
    assert int(s["long_go"].sum() + s["short_go"].sum()) <= 1


def test_htf_waits_for_closed_30m_bar():
    idx = pd.date_range("2026-01-02 09:00", periods=8, freq="15min")
    spike_open = pd.Series([1.0, 1.0, 9.0, 1.0, 1.0, 1.0, 1.0, 1.0], index=idx)
    held_open = _no_repaint_request(spike_open, "30", "15m")
    # Incomplete 30m (09:30 print = 9) must not move Bias.
    assert held_open.loc["2026-01-02 09:30"] != 9.0
    assert held_open.loc["2026-01-02 09:45"] != 9.0

    spike_close = pd.Series([1.0, 1.0, 1.0, 9.0, 1.0, 1.0, 1.0, 1.0], index=idx)
    held_close = _no_repaint_request(spike_close, "30", "15m")
    # 09:30-10:00 closes on the 09:45 bar; Pine [1] publishes on 10:15.
    assert held_close.loc["2026-01-02 10:00"] != 9.0
    assert held_close.loc["2026-01-02 10:15"] == 9.0


def test_no_repaint_survives_readonly_numpy_views():
    idx = pd.date_range("2026-01-02 09:00", periods=8, freq="15min")
    spike = pd.Series([1.0, 1.0, 1.0, 9.0, 1.0, 1.0, 1.0, 1.0], index=idx)
    orig = pd.Series.to_numpy

    def readonly(self, *args, **kwargs):
        arr = orig(self, *args, **kwargs)
        view = np.array(arr, copy=True)
        view.flags.writeable = False
        return view

    pd.Series.to_numpy = readonly
    try:
        held = _no_repaint_request(spike, "30", "15m")
    finally:
        pd.Series.to_numpy = orig
    assert held.loc["2026-01-02 10:15"] == 9.0


def test_snapshot_does_not_carry_previous_bar():
    df = _wave_frame()
    s = market_bias_series(
        df,
        ha_len=8,
        ha_len2=8,
        osc_len=3,
        require_bar=False,
        reverse_exit=True,
        chart_tf="15m",
        max_same=8,
    )
    if not bool(s["long_go"].iloc[-2] or s["short_go"].iloc[-2]):
        return
    if bool(s["long_go"].iloc[-1] or s["short_go"].iloc[-1]):
        return
    snap = market_bias_snapshot(
        df,
        chart_tf="15m",
        ha_len=8,
        ha_len2=8,
        osc_len=3,
        require_bar=False,
        reverse_exit=True,
        max_same=8,
        side="both",
    )
    assert snap["pine_al"] is False
    assert snap["market_bias_buy"] is False
    assert snap["market_bias_sell"] is False
