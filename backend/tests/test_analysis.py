"""Gate selection must ignore anything published after 09:50 London."""

import json
import math
from datetime import date

import pytest

from app.analysis import (
    build_day,
    build_report,
    canonical,
    gate_deadline,
    summarise,
)
from app.store import default_data_path


def test_gate_is_0950_london_on_the_previous_morning():
    assert canonical(gate_deadline(date(2026, 1, 15))) == "2026-01-14T09:50:00Z"
    assert canonical(gate_deadline(date(2026, 1, 1))) == "2025-12-31T09:50:00Z"


def test_latest_pre_gate_forecast_is_held_across_the_hour():
    actuals = [
        {
            "startTime": "2026-01-15T00:00:00Z",
            "settlementDate": "2026-01-15",
            "settlementPeriod": 1,
            "generation": 80,
        },
        {
            "startTime": "2026-01-15T00:30:00Z",
            "settlementDate": "2026-01-15",
            "settlementPeriod": 2,
            "generation": 90,
        },
    ]
    forecasts = [
        {
            "startTime": "2026-01-15T00:00:00Z",
            "publishTime": "2026-01-14T07:30:00Z",
            "generation": 100,
        },
        {
            "startTime": "2026-01-15T00:00:00Z",
            "publishTime": "2026-01-14T09:30:00Z",
            "generation": 200,
        },
        {
            "startTime": "2026-01-15T00:00:00Z",
            "publishTime": "2026-01-14T11:30:00Z",
            "generation": 999,
        },
    ]
    day = build_day(date(2026, 1, 15), actuals, forecasts)
    paired = [point for point in day["points"] if point["forecastMw"] is not None]
    assert [point["settlementPeriod"] for point in paired] == [1, 2]
    assert [point["forecastMw"] for point in paired] == [200, 200]
    assert [point["errorMw"] for point in paired] == [120, 110]
    assert day["forecastPublishTime"] == "2026-01-14T09:30:00Z"
    assert day["gateTime"] == "2026-01-14T09:50:00Z"
    assert day["summary"]["maeMw"] == 115
    assert day["summary"]["biasMw"] == 115
    assert day["summary"]["energyErrorMwh"] == 115
    assert day["summary"]["absoluteEnergyErrorMwh"] == 115
    assert day["summary"]["intervals"] == 48
    assert day["summary"]["missingForecastIntervals"] == 46
    assert day["summary"]["missingActualIntervals"] == 46
    assert all(point["forecastMw"] is None for point in day["points"] if point["settlementPeriod"] > 2)
    assert day["summary"]["rmseMw"] == math.sqrt((120**2 + 110**2) / 2)


def test_exact_gate_is_kept_and_a_later_publish_is_dropped():
    forecasts = [
        {
            "startTime": "2026-01-15T12:00:00Z",
            "publishTime": "2026-01-14T09:50:00Z",
            "generation": 5,
        },
        {
            "startTime": "2026-01-15T12:00:00Z",
            "publishTime": "2026-01-14T09:50:01Z",
            "generation": 50,
        },
    ]
    actuals = [
        {"startTime": "2026-01-15T12:00:00Z", "generation": 4},
        {"startTime": "2026-01-15T12:30:00Z", "generation": 6},
    ]
    day = build_day(date(2026, 1, 15), actuals, forecasts)
    noon = [point for point in day["points"] if point["settlementPeriod"] in (25, 26)]
    assert [point["forecastMw"] for point in noon] == [5, 5]
    assert [point["publishTime"] for point in noon] == [
        "2026-01-14T09:50:00Z",
        "2026-01-14T09:50:00Z",
    ]


def test_same_morning_forecast_cannot_score_its_own_delivery_day():
    forecasts = [
        {
            "startTime": "2026-01-16T00:00:00Z",
            "publishTime": "2026-01-15T09:30:00Z",
            "generation": 40,
        },
        {
            "startTime": "2026-01-16T00:00:00Z",
            "publishTime": "2026-01-15T11:30:00Z",
            "generation": 80,
        },
    ]
    actuals = [{"startTime": "2026-01-16T00:00:00Z", "generation": 30}]
    day = build_day(date(2026, 1, 16), actuals, forecasts)
    first = day["points"][0]
    assert first["forecastMw"] == 40
    assert first["publishTime"] == "2026-01-15T09:30:00Z"


def test_summarise_uses_overlap_for_error_and_keeps_unmatched_energy():
    points = [
        {
            "startTime": "2026-01-15T00:00:00Z",
            "settlementPeriod": 1,
            "forecastMw": 10,
            "actualMw": 8,
            "errorMw": 2,
            "publishTime": "2026-01-14T09:30:00Z",
        },
        {
            "startTime": "2026-01-15T00:30:00Z",
            "settlementPeriod": 2,
            "forecastMw": 10,
            "actualMw": 12,
            "errorMw": -2,
            "publishTime": "2026-01-14T09:30:00Z",
        },
        {
            "startTime": "2026-01-15T01:00:00Z",
            "settlementPeriod": 3,
            "forecastMw": 5,
            "actualMw": 5,
            "errorMw": 0,
            "publishTime": "2026-01-14T09:30:00Z",
        },
        {
            "startTime": "2026-01-15T01:30:00Z",
            "settlementPeriod": 4,
            "forecastMw": None,
            "actualMw": 5,
            "errorMw": None,
            "publishTime": None,
        },
    ]
    summary = summarise(points)
    assert summary["paired"] == 3
    assert summary["biasMw"] == 0
    assert summary["maeMw"] == 4 / 3
    assert summary["rmseMw"] == math.sqrt(8 / 3)
    assert summary["energyErrorMwh"] == 0
    assert summary["absoluteEnergyErrorMwh"] == 2
    assert summary["intervals"] == 4
    assert summary["forecastIntervals"] == 3
    assert summary["actualIntervals"] == 4
    assert summary["missingForecastIntervals"] == 1
    assert summary["missingActualIntervals"] == 0
    assert summary["forecastMwh"] == 12.5
    assert summary["actualMwh"] == 15
    assert summary["hourlyPaired"] == 2
    assert summary["hourlyBiasMw"] == 0
    assert summary["p10Mw"] == -1.6
    assert summary["p50Mw"] == 0
    assert summary["p90Mw"] == 1.6


def test_zero_megawatts_is_kept_and_a_gap_stays_blank():
    day = build_day(
        date(2026, 1, 15),
        [{"startTime": "2026-01-15T00:00:00Z", "generation": 0}],
        [],
    )
    first = day["points"][0]
    assert first["actualMw"] == 0
    assert first["forecastMw"] is None
    assert first["errorMw"] is None
    assert day["summary"]["actualMwh"] == 0
    assert day["summary"]["energyErrorMwh"] is None
    assert day["summary"]["missingForecastIntervals"] == 48


def test_month_report_covers_every_january_day():
    report = build_report([], [])
    assert len(report["dayList"]) == 31
    assert report["accuracy"]["expected"] == 31 * 48
    assert report["accuracy"]["paired"] == 0
    assert report["days"]["2026-01-01"]["points"][0]["settlementPeriod"] == 1


def test_real_snapshot_never_uses_a_post_gate_forecast():
    path = default_data_path()
    if not path.exists():
        pytest.skip("snapshot not built yet")
    snapshot = json.loads(path.read_text())
    report = build_report(snapshot["actuals"], snapshot["forecasts"])
    assert len(snapshot["actuals"]) == 31 * 48
    assert report["accuracy"]["paired"] == 31 * 48
    assert report["accuracy"]["intervals"] == 31 * 48
    assert report["accuracy"]["missingForecastIntervals"] == 0
    assert report["accuracy"]["missingActualIntervals"] == 0
    assert report["accuracy"]["absoluteEnergyErrorMwh"] >= abs(report["accuracy"]["energyErrorMwh"])
    expected_vintage = {
        "2026-01-01": "2025-12-31T09:30:00Z",
        "2026-01-15": "2026-01-14T09:30:00Z",
        "2026-01-31": "2026-01-30T09:30:00Z",
    }
    for day in report["dayList"]:
        gate = day["gateTime"]
        assert day["summary"]["paired"] == 48
        for point in day["points"]:
            assert point["publishTime"] is not None
            assert point["publishTime"] <= gate
            assert point["actualMw"] is not None
            assert point["forecastMw"] is not None
        if day["date"] in expected_vintage:
            assert day["forecastPublishTime"] == expected_vintage[day["date"]]
    last = report["days"]["2026-01-15"]["points"][-1]
    assert last["startTime"] == "2026-01-15T23:30:00Z"
    assert last["settlementPeriod"] == 48
