from types import SimpleNamespace

from app.services.alarm_service import list_viop_pay_contracts
from app.services.optimize_review import (
    REVIEW_EXTRA,
    REVIEW_TOP,
    alarm_for_contract,
    build_symbol_review,
    improvement_reasons,
    pine_overrides_from_public,
    reference_from_overrides,
    run_to_dict,
)


def _row(**kwargs):
    base = {
        "rank": 1,
        "passed": True,
        "tag": "",
        "win_rate": 60,
        "profit_factor": 1.8,
        "net_profit_pct": 22,
        "max_drawdown": 8,
        "trades": 20,
        "params": {"ha_len": 64, "ha_len2": 72, "osc_len": 7, "ha_htf": "30", "exitMode": "Swing RR", "rrMult": 1.6},
    }
    base.update(kwargs)
    return base


def test_improvement_reasons_need_better_metrics():
    ref = {"win_rate": 50, "profit_factor": 1.4, "net_profit_pct": 10, "max_drawdown": 9}
    reasons = improvement_reasons(_row(), ref)
    assert any("PF" in r for r in reasons)
    assert any("WR" in r for r in reasons)
    assert any("Kâr" in r for r in reasons)


def test_improvement_reasons_reject_much_worse_drawdown():
    ref = {"win_rate": 50, "profit_factor": 1.4, "net_profit_pct": 10, "max_drawdown": 5}
    assert improvement_reasons(_row(max_drawdown=12), ref) == []


def test_build_symbol_review_keeps_top_five_and_extras():
    rows = []
    for i in range(12):
        rows.append(
            _row(
                rank=i + 1,
                profit_factor=2.0 + i * 0.01,
                win_rate=55 + i,
                net_profit_pct=15 + i,
            )
        )
    result = {
        "symbol": "AEFES1!",
        "name": "Anadolu Efes",
        "tested": 12,
        "passed": 12,
        "reference": {"win_rate": 40, "profit_factor": 1.1, "net_profit_pct": 5, "max_drawdown": 12},
        "results": rows,
    }
    alarm = {"id": 3, "name": "AEFES alarm", "timeframe": "30m"}
    out = build_symbol_review(result, alarm)
    assert out["symbol"] == "AEFES1!"
    assert len(out["recommendations"]) == REVIEW_TOP
    assert len(out["extras"]) == 7
    assert len(out["extras"]) <= REVIEW_EXTRA
    assert out["recommendations"][0]["pine_overrides"]["ha_len"] == 64
    assert "AEFES alarm" in out["note"]


def test_build_symbol_review_without_alarm_proposes_five_sets():
    rows = []
    for i in range(8):
        rows.append(
            _row(
                rank=i + 1,
                passed=i < 2,
                profit_factor=2.2 - i * 0.1,
                win_rate=70 - i,
                net_profit_pct=24 - i,
            )
        )
    rows.append(_row(rank=99, passed=False, trades=0, profit_factor=9, win_rate=99, net_profit_pct=99))
    result = {"symbol": "SISE1!", "results": rows, "reference": None}
    out = build_symbol_review(result, None)
    assert out["alarm"] is None
    assert len(out["recommendations"]) == REVIEW_TOP
    assert all(r["trades"] for r in out["recommendations"])
    assert out["recommendations"][0]["passed"] is True
    assert "alarm kurma" in out["note"]
    assert any("yeni alarm" in (r["reasons"][0] if r["reasons"] else "") for r in out["recommendations"])


def test_pine_overrides_and_reference_roundtrip():
    ov = pine_overrides_from_public({"ha_len": 80, "ha_len2": 96, "osc_len": 7, "ha_htf": "30", "exitMode": "Percent", "tp_pct": 2, "sl_pct": 1})
    ref = reference_from_overrides(ov)
    assert ref["enabled"] is True
    assert ref["ha_len"] == 80
    assert ref["exit_mode"] == "Percent"
    assert reference_from_overrides({}) is None


def test_run_to_dict_counts_remaining_while_running():
    row = SimpleNamespace(
        id=9,
        status="running",
        started_at=None,
        finished_at=None,
        current_symbol="AEFES1!",
        done_count=5,
        total_count=47,
        error_message=None,
        config_json="{}",
        report_json='{"symbols":[{"symbol":"AKBNK1!","recommendations":[{},{}]}]}',
    )
    out = run_to_dict(row)
    assert out["done_count"] == 5
    assert out["remaining_count"] == 41
    assert "AEFES1!" in out["summary"]
    assert "5/47" in out["summary"]


def test_alarm_for_contract_prefers_enabled_matching_timeframe():
    rows = [
        SimpleNamespace(
            id=1,
            name="old 15m",
            enabled=True,
            config_json='{"alarm": true, "timeframe": "15m", "custom_symbols": "AEFES1!", "pine_input_overrides": {"ha_len": 40}}',
        ),
        SimpleNamespace(
            id=2,
            name="aefes 30m",
            enabled=True,
            config_json='{"alarm": true, "timeframe": "30m", "custom_symbols": "AEFES1!,AKBNK1!", "pine_input_overrides": {"ha_len": 80}}',
        ),
        SimpleNamespace(
            id=3,
            name="disabled 30m",
            enabled=False,
            config_json='{"alarm": true, "timeframe": "30m", "custom_symbols": "AEFES1!", "pine_input_overrides": {"ha_len": 10}}',
        ),
    ]

    class _Q:
        def order_by(self, *_a):
            return self

        def all(self):
            return rows

    class _Db:
        def query(self, _model):
            return _Q()

    hit = alarm_for_contract(_Db(), "AEFES1!", "30m")
    assert hit["id"] == 2
    assert hit["overrides"]["ha_len"] == 80


def test_pay_universe_has_forty_seven_contracts():
    rows = list_viop_pay_contracts()
    assert len(rows) == 47
    assert any(r["contract"] == "AEFES1!" for r in rows)
