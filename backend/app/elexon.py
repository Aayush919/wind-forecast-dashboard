"""Thin client for the public Elexon Insights stream endpoints."""

from __future__ import annotations

import time
from datetime import date, timedelta

import httpx

from app.config import ELEXON_BASE

RETRYABLE = {429, 500, 502, 503, 504}
HEADERS = {
    "Accept": "application/json",
    "User-Agent": "day-ahead-wind-desk/1.0",
}


def _rows(payload) -> list[dict]:
    """Accept only a list of rows, or an object whose data field is that list.

    A missing data field is a schema error. It is not an empty month.
    A row without startTime and generation is a schema error too.
    """
    if isinstance(payload, dict):
        if "data" not in payload:
            raise RuntimeError("Elexon response is missing data")
        payload = payload["data"]
    if not isinstance(payload, list):
        raise RuntimeError("Elexon response was not a list of rows")
    for row in payload:
        if not isinstance(row, dict) or "startTime" not in row or "generation" not in row:
            raise RuntimeError("Elexon row is missing startTime or generation")
    return payload


def request_rows(client: httpx.Client, dataset: str, params: dict) -> list[dict]:
    url = f"{ELEXON_BASE}/{dataset}/stream"
    delay = 1.0
    last_status = None
    for attempt in range(6):
        try:
            response = client.get(url, params=params)
        except httpx.HTTPError as exc:
            if attempt == 5:
                raise RuntimeError(f"{dataset} request failed: {exc}") from exc
            time.sleep(delay)
            delay *= 2
            continue
        last_status = response.status_code
        if response.status_code in RETRYABLE:
            time.sleep(delay)
            delay *= 2
            continue
        response.raise_for_status()
        return _rows(response.json())
    raise RuntimeError(f"{dataset} still failing after retries (last status {last_status})")


def each_day(start: date, end: date):
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def fetch_actuals(client: httpx.Client, start: date, end: date) -> list[dict]:
    rows: list[dict] = []
    for day in each_day(start, end):
        chunk = request_rows(
            client,
            "FUELHH",
            {
                "settlementDateFrom": day.isoformat(),
                "settlementDateTo": day.isoformat(),
                "fuelType": "WIND",
            },
        )
        print(f"FUELHH {day.isoformat()} {len(chunk)} rows", flush=True)
        rows.extend(chunk)
    return rows


def fetch_forecasts(client: httpx.Client, start: date, end: date) -> list[dict]:
    rows: list[dict] = []
    for day in each_day(start, end):
        nxt = day + timedelta(days=1)
        chunk = request_rows(
            client,
            "WINDFOR",
            {
                "publishDateTimeFrom": f"{day.isoformat()}T00:00:00Z",
                "publishDateTimeTo": f"{nxt.isoformat()}T00:00:00Z",
            },
        )
        print(f"WINDFOR {day.isoformat()} {len(chunk)} rows", flush=True)
        rows.extend(chunk)
    return rows
