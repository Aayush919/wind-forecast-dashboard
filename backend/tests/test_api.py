"""The desk endpoints return the same pre-gate series the scorer builds."""

import json

import pytest
from fastapi.testclient import TestClient

from app import store
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    snapshot = {
        "ingestedAt": "2026-10-25T00:00:00Z",
        "publishFrom": "2025-12-30",
        "publishTo": "2026-02-01",
        "deliveryFrom": "2026-01-01",
        "deliveryTo": "2026-01-31",
        "actuals": [
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
        ],
        "forecasts": [
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
        ],
    }
    path = tmp_path / "january_2026.json"
    path.write_text(json.dumps(snapshot))
    monkeypatch.setenv("DATA_FILE", str(path))
    store.reset()
    with TestClient(app) as test_client:
        yield test_client
    store.reset()


def test_health_meta_days_and_accuracy(client):
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["dataReady"] is True

    meta = client.get("/api/meta")
    assert meta.status_code == 200
    body = meta.json()
    assert body["gateLocal"] == "09:50"
    assert body["gateIsAssumption"] is True
    assert "Business assumption" in body["gateRule"]
    assert body["errorDefinition"] == "forecast minus actual"
    assert body["actualRows"] == 2
    assert body["forecastRows"] == 3

    days = client.get("/api/days")
    assert days.status_code == 200
    listed = days.json()["days"]
    assert len(listed) == 31
    january_15 = next(day for day in listed if day["date"] == "2026-01-15")
    assert january_15["forecastPublishTime"] == "2026-01-14T09:30:00Z"
    assert january_15["maeMw"] == 115
    assert "points" not in january_15

    day = client.get("/api/days/2026-01-15")
    assert day.status_code == 200
    payload = day.json()
    assert payload["gateTime"] == "2026-01-14T09:50:00Z"
    first = payload["points"][0]
    assert first["forecastMw"] == 200
    assert first["actualMw"] == 80
    assert first["errorMw"] == 120
    assert first["publishTime"] == "2026-01-14T09:30:00Z"

    accuracy = client.get("/api/accuracy")
    assert accuracy.status_code == 200
    scored = accuracy.json()
    assert scored["paired"] == 2
    assert scored["expected"] == 31 * 48
    assert scored["energyErrorMwh"] == 115
    assert scored["absoluteEnergyErrorMwh"] == 115
    assert scored["intervals"] == 31 * 48
    assert scored["missingForecastIntervals"] == (31 * 48) - 2
    assert scored["missingActualIntervals"] == (31 * 48) - 2
    assert day.json()["summary"]["missingForecastIntervals"] == 46
    assert len(scored["byDay"]) == 31
    assert len(scored["byPeriod"]) == 48
    assert scored["byPeriod"][0]["label"] == "00:00"
    assert scored["byPeriod"][0]["maeMw"] == 120


def test_bad_dates(client):
    assert client.get("/api/days/15-01-2026").status_code == 400
    assert client.get("/api/days/2026-02-01").status_code == 404
