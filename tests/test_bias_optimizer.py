import numpy as np
import pandas as pd

from app.services.bias_optimizer import (
    MAX_COMBOS,
    SCAN_ALL_MAX,
    build_grid,
    build_strategy_chart,
    chart_from_frame,
    coarsen_grid,
    coarsen_values,
    combo_budget,
    combo_passes,
    describe_search_plan,
    expand_combos,
    grid_space,
    neighborhood_grid,
    neighborhood_values,
    numeric_span,
    parse_reference,
    refine_strides,
    search_bias_params,
)
from app.services.borsapy_client import coverage_note
from app.services.pine_market_bias import market_bias_series, summarize_bias_trades


def _combo_key(combo: dict) -> tuple:
    return tuple(sorted(combo.items()))


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


def test_strategy_chart_equity_and_months():
    trades = [
        {"side": "long", "pnl_pct": 10, "reason": "target", "entry_time": "2025-09-02T10:00:00", "exit_time": "2025-09-10T12:00:00"},
        {"side": "short", "pnl_pct": -5, "reason": "stop", "entry_time": "2025-10-01T10:00:00", "exit_time": "2025-10-03T12:00:00"},
    ]
    chart = build_strategy_chart(trades, start_equity=10000)
    assert chart["equity"][0]["equity"] == 10000
    assert abs(chart["end_equity"] - 10000 * 1.1 * 0.95) < 0.05
    assert [m["period"] for m in chart["months"]] == ["2025-09", "2025-10"]
    assert chart["months"][0]["pnl"] > 0
    assert chart["months"][1]["pnl"] < 0


def test_chart_from_frame_returns_curve():
    df = _wave_frame()
    out = chart_from_frame(
        df,
        chart_tf="15m",
        params={
            "ha_len": 8,
            "ha_len2": 8,
            "osc_len": 3,
            "ha_htf": "",
            "exitMode": "Percent",
            "rrMult": 1.0,
            "swingBars": 4,
            "tp_pct": 2.0,
            "sl_pct": 1.0,
            "allow_long": True,
            "allow_short": True,
            "reverse_exit": True,
            "require_bar": False,
            "maxSame": 8,
        },
    )
    assert out["metrics"]["trades"] >= 1
    assert len(out["equity"]) >= 2
    assert out["params"]["exitMode"] == "Percent"


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


def test_search_emits_partial_snapshots():
    df = _wave_frame(360)
    combo = {
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
    }
    seen = []

    def on_snapshot(payload):
        seen.append(payload["tested"])
        assert payload["partial"] is True
        assert payload["results"]

    found = search_bias_params(
        df,
        chart_tf="15m",
        combos=[combo, dict(combo), dict(combo)],
        filters={
            "min_win_rate": 0,
            "max_drawdown": 100,
            "min_profit_factor": 0,
            "min_profit": -100,
            "min_trades": 1,
        },
        on_snapshot=on_snapshot,
        total=3,
    )
    assert seen
    assert seen[0] == 1
    assert seen[-1] >= 1
    assert found["tested"] == 3
    assert found["partial"] is False


def test_search_stops_when_requested():
    df = _wave_frame(360)
    combo = {
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
    }
    hits = {"n": 0}

    def should_stop():
        hits["n"] += 1
        return hits["n"] > 1

    found = search_bias_params(
        df,
        chart_tf="15m",
        combos=[combo, dict(combo), dict(combo)],
        filters={
            "min_win_rate": 0,
            "max_drawdown": 100,
            "min_profit_factor": 0,
            "min_profit": -100,
            "min_trades": 1,
        },
        should_stop=should_stop,
    )
    assert found["cancelled"] is True
    assert found["tested"] == 1
    assert len(found["results"]) == 1


def test_cancel_optimize_job_flags_running():
    from app.services.bias_optimizer import (
        OptimizeJob,
        _jobs,
        _lock,
        cancel_optimize_job,
    )

    job = OptimizeJob(id="stop-test")
    with _lock:
        _jobs["stop-test"] = job
    try:
        out = cancel_optimize_job("stop-test")
        assert out is not None
        assert job.cancel_requested is True
        assert out["message"] == "Durduruluyor…"
        assert cancel_optimize_job("missing-job") is None
    finally:
        with _lock:
            _jobs.pop("stop-test", None)


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


def test_small_grid_enumerates_all_when_under_cap():
    grid = build_grid(
        {
            "mode": "quick",
            "ha_len": {"start": 48, "stop": 80, "step": 16},
            "ha_len2": {"start": 72, "stop": 96, "step": 24},
            "osc_len": {"start": 7, "stop": 11, "step": 4},
            "exit_mode": "Swing RR",
            "optimize": {
                "ha_htf": False,
                "exit_mode": False,
                "rr_mult": False,
                "swing_bars": False,
                "tp_pct": False,
                "sl_pct": False,
                "max_same": False,
                "reverse_exit": False,
                "require_bar": False,
            },
        }
    )
    space = grid_space(grid)
    combos = expand_combos(grid, max_combos=20000, seed=1)
    assert space <= 20000
    assert len(combos) == space
    assert combo_budget({"scan_all": True}, space) == space
    assert combo_budget({"scan_all": True}, MAX_COMBOS + 1) == MAX_COMBOS + 1
    try:
        combo_budget({"scan_all": True}, SCAN_ALL_MAX + 1)
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "Tamamını tara" in str(exc)


def _wide_sample_grid():
    return build_grid(
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


def test_capped_grid_keeps_start_and_classic():
    grid = _wide_sample_grid()
    combos = expand_combos(grid, max_combos=180, seed=1)
    assert len(combos) == 180
    assert any(c["ha_len"] == 48 and c["ha_len2"] == 55 and c["osc_len"] == 5 for c in combos)
    assert any(c["ha_len"] == 100 and c["ha_len2"] == 100 and c["osc_len"] == 7 for c in combos)


def test_qmc_sample_is_deterministic_and_spreads():
    grid = _wide_sample_grid()
    a = expand_combos(grid, max_combos=180, seed=7)
    b = expand_combos(grid, max_combos=180, seed=7)
    assert a == b
    assert len({_combo_key(c) for c in a}) == 180
    ha = [c["ha_len"] for c in a]
    bins = [0] * 8
    for val in ha:
        t = (val - 48) / (200 - 48)
        bins[min(7, max(0, int(t * 8)))] += 1
    assert min(bins) >= 1
    assert any(
        c["ha_len"] not in (48, 100, 200)
        and c["ha_len2"] not in (55, 100, 200)
        and c["osc_len"] not in (5, 7, 20)
        for c in a
    )


def test_qmc_sample_fills_joint_ha_space():
    grid = _wide_sample_grid()
    qmc = expand_combos(grid, max_combos=400, seed=3)
    assert len(qmc) == 400
    pairs = {(c["ha_len"], c["ha_len2"]) for c in qmc}
    assert len(pairs) >= 280


def test_coarsen_keeps_endpoints_and_stride():
    vals = list(range(48, 201))
    out = coarsen_values(vals, 4)
    assert out[0] == 48
    assert out[-1] == 200
    assert out[1] - out[0] == 4
    assert 64 in out


def test_wide_grid_adds_coarse_tours_until_cap():
    grid = _wide_sample_grid()
    strides = refine_strides(grid, 20000)
    assert strides[-3:] == [4, 2, 1]
    assert strides[0] >= 8
    assert grid_space(coarsen_grid(grid, strides[0])) <= 20000 or strides[0] >= 256
    plan = describe_search_plan(
        {
            "mode": "quick",
            "max_combos": 20000,
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
    assert plan["mode"] == "refine"
    assert plan["tours"] == len(plan["strides"])
    assert plan["extra_tours"] >= 1
    assert plan["strides"][-1] == 1


def test_neighborhood_stays_on_next_stride():
    vals = list(range(48, 201))
    around = neighborhood_values(vals, [64], prev_stride=4, next_stride=2)
    assert 64 in around
    assert all((v - 48) % 2 == 0 or v == 64 for v in around)
    assert min(around) >= 60
    assert max(around) <= 68
    grid = _wide_sample_grid()
    seeds = [{"params": {"ha_len": 64, "ha_len2": 100, "osc_len": 7, "rrMult": 1.0, "swingBars": 8, "maxSame": 1, "ha_htf": "30"}}]
    nb = neighborhood_grid(grid, seeds, 4, 2)
    assert 64 in nb["ha_len"]
    assert nb["reverse_exit"] == grid["reverse_exit"]


def test_small_grid_plan_is_single_full_tour():
    plan = describe_search_plan(
        {
            "mode": "quick",
            "max_combos": 20000,
            "ha_len": {"start": 48, "stop": 80, "step": 16},
            "ha_len2": {"start": 72, "stop": 96, "step": 24},
            "osc_len": {"start": 7, "stop": 11, "step": 4},
            "exit_mode": "Swing RR",
            "optimize": {
                "ha_htf": False,
                "exit_mode": False,
                "rr_mult": False,
                "swing_bars": False,
                "tp_pct": False,
                "sl_pct": False,
                "max_same": False,
                "reverse_exit": False,
                "require_bar": False,
            },
        }
    )
    assert plan["mode"] == "full"
    assert plan["tours"] == 1


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


def test_parse_reference_and_tag_in_results():
    ref = parse_reference(
        {
            "side": "both",
            "reference": {
                "enabled": True,
                "ha_len": 100,
                "ha_len2": 100,
                "osc_len": 7,
                "ha_htf": "30",
                "exit_mode": "Swing RR",
                "rr_mult": 1.5,
                "swing_bars": 8,
                "reverse_exit": "true",
                "require_bar": "false",
                "max_same": 2,
            },
        }
    )
    assert ref["ha_len"] == 100
    assert ref["_tag"] == "referans"
    df = _wave_frame(240)
    found = search_bias_params(
        df,
        chart_tf="15m",
        combos=[ref],
        filters={
            "min_win_rate": 0,
            "max_drawdown": 100,
            "min_profit_factor": 0,
            "min_profit": -100,
            "min_trades": 1,
        },
    )
    assert found["reference"]
    assert found["reference"]["tag"] == "referans"
    assert found["results"][0]["tag"] == "referans"


def test_format_eta_and_progress_label():
    from app.services.bias_optimizer import _search_progress_label, format_eta

    assert format_eta(3) == "birkaç sn"
    assert format_eta(40) == "40 sn"
    assert "dk" in format_eta(120)
    assert "gün" in format_eta(48 * 3600)
    label = _search_progress_label(80, 145, 145, pct=55.17, eta="1 dk")
    assert "80/145" in label
    assert "%55" in label
    assert "~1 dk kaldı" in label


def test_coverage_note_for_short_15m():
    assert coverage_note("15m", "13mo", 240)
    assert coverage_note("30m", "13mo", 400) == ""


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
