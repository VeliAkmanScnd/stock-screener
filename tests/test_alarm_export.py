import zipfile
from io import BytesIO

from app.services.alarm_service import alarm_export_table, build_alarms_xlsx


def test_alarm_export_flattens_settings_and_pine_params():
    alarms = [
        {
            "id": 1,
            "name": "AEFES Bias",
            "enabled": True,
            "pine_script_id": 7,
            "pine_input_overrides": {"ha_len": 70, "ha_len2": 91},
            "contracts": ["AEFES1!", "AKBNK1!"],
            "timeframe": "15m",
            "hour": 9,
            "minute": 1,
            "end_hour": 18,
            "weekdays": [0, 1, 2, 3, 4],
            "timezone": "Europe/Istanbul",
            "notify_telegram": True,
            "telegram_to": "-100",
            "last_run_istanbul": None,
            "next_run_istanbul": "2026-11-04 10:01",
            "last_status": "ok",
            "last_match_count": 2,
            "last_error": "",
            "created_at": "2026-11-01T10:00:00",
        },
        {
            "id": 2,
            "name": "Kapalı",
            "enabled": False,
            "pine_script_id": 7,
            "pine_input_overrides": {"osc_len": 14},
            "contracts": ["THYAO1!"],
            "timeframe": "30m",
            "hour": 10,
            "minute": 1,
            "end_hour": 17,
            "weekdays": [0, 2, 4],
            "timezone": "Europe/Istanbul",
            "notify_telegram": False,
            "telegram_to": "",
            "last_run_istanbul": "",
            "next_run_istanbul": "",
            "last_status": "",
            "last_match_count": None,
            "last_error": "",
            "created_at": "",
        },
    ]
    headers, rows = alarm_export_table(alarms, {7: "Market Bias"})
    assert "ad" in headers
    assert "pine" in headers
    assert "param_ha_len" in headers
    assert "param_osc_len" in headers
    assert len(rows) == 2
    first = dict(zip(headers, rows[0]))
    assert first["ad"] == "AEFES Bias"
    assert first["pine"] == "Market Bias"
    assert first["gunler"] == "Pzt,Sal,Çar,Per,Cum"
    assert first["kontrat_sayisi"] == 2
    assert first["param_ha_len"] == 70
    assert first["param_osc_len"] == ""
    blob = build_alarms_xlsx(headers, rows)
    assert blob[:2] == b"PK"
    with zipfile.ZipFile(BytesIO(blob)) as zf:
        names = set(zf.namelist())
        assert "xl/worksheets/sheet1.xml" in names
        sheet = zf.read("xl/worksheets/sheet1.xml").decode("utf-8")
        assert "AEFES Bias" in sheet
        assert "Market Bias" in sheet
        assert "param_ha_len" in sheet
