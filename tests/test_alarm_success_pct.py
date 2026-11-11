from app.services.alarm_service import (
    build_scan_config,
    format_success_pct_label,
    normalize_success_pct,
)
from app.services.telegram_service import format_signal_telegram_card


def test_normalize_success_pct_clamps_and_parses():
    assert normalize_success_pct(None) is None
    assert normalize_success_pct("") is None
    assert normalize_success_pct("  ") is None
    assert normalize_success_pct("72%") == 72.0
    assert normalize_success_pct("72,5") == 72.5
    assert normalize_success_pct(150) == 100.0
    assert normalize_success_pct(-3) == 0.0


def test_format_success_pct_label_na_when_empty():
    assert format_success_pct_label(None) == "N/A"
    assert format_success_pct_label("") == "N/A"
    assert format_success_pct_label(72) == "72%"
    assert format_success_pct_label(72.5) == "72.5%"


def test_build_scan_config_stores_success_pct():
    cfg = build_scan_config(
        pine_script_id=1,
        pine_input_overrides={},
        contracts=["AEFES1!"],
        timeframe="15m",
        success_pct="81",
    )
    assert cfg["success_pct"] == 81.0
    empty = build_scan_config(
        pine_script_id=1,
        pine_input_overrides={},
        contracts=["AEFES1!"],
        timeframe="15m",
        success_pct=None,
    )
    assert empty["success_pct"] is None


def test_telegram_card_includes_success_or_na():
    with_pct = format_signal_telegram_card(
        "AEFES1!",
        100.0,
        "AL",
        market="viop",
        scan_name="AEFES Bias",
        success_pct=72,
        include_success_pct=True,
    )
    assert "Başarı\t: 72%" in with_pct
    blank = format_signal_telegram_card(
        "AEFES1!",
        100.0,
        "AL",
        market="viop",
        scan_name="AEFES Bias",
        success_pct=None,
        include_success_pct=True,
    )
    assert "Başarı\t: N/A" in blank
    hidden = format_signal_telegram_card(
        "AEFES1!",
        100.0,
        "AL",
        market="viop",
        scan_name="Normal tarama",
    )
    assert "Başarı" not in hidden
