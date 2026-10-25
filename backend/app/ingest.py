"""Pull January 2026 wind actuals and forecasts from Elexon and cache them.

Run from the backend directory:

    python -m app.ingest
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx

from app.analysis import (
    as_mw,
    build_report,
    canonical,
    collect_actuals,
    delivery_dates,
    half_hours,
    hour_start,
    on_forecast_hour,
    try_parse_time,
)
from app.config import DELIVERY_FROM, DELIVERY_TO, LONDON, PUBLISH_FROM, PUBLISH_TO
from app.elexon import HEADERS, fetch_actuals, fetch_forecasts
from app.store import default_data_path


def _in_delivery_month(moment) -> bool:
    return DELIVERY_FROM <= moment.astimezone(LONDON).date() <= DELIVERY_TO


def clean_actuals(rows: list[dict]) -> list[dict]:
    records, _quality = collect_actuals(rows, delivery_month_only=True)
    return records


def clean_forecasts(rows: list[dict]) -> list[dict]:
    cleaned = {}
    for row in rows:
        generation = as_mw(row.get("generation"))
        start = row.get("startTime")
        published = row.get("publishTime")
        if generation is None or not start or not published:
            continue
        start_at = try_parse_time(start)
        published_at = try_parse_time(published)
        if start_at is None or published_at is None or not on_forecast_hour(start_at):
            continue
        if not _in_delivery_month(start_at):
            continue
        start_key = canonical(start_at)
        publish_key = canonical(published_at)
        bucket = cleaned.setdefault((publish_key, start_key), [])
        bucket.append(generation)
    records = []
    for key in sorted(cleaned):
        values = cleaned[key]
        record = {
            "startTime": key[1],
            "publishTime": key[0],
            "generation": values[-1],
        }
        if len(values) > 1:
            record["duplicate"] = True
            if len(set(values)) > 1:
                record["duplicateConflict"] = True
        records.append(record)
    return records


def build_snapshot(actual_rows: list[dict], forecast_rows: list[dict]) -> dict:
    actuals, quality = collect_actuals(actual_rows, delivery_month_only=True)
    forecasts = clean_forecasts(forecast_rows)
    return {
        "ingestedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "publishFrom": PUBLISH_FROM.isoformat(),
        "publishTo": PUBLISH_TO.isoformat(),
        "deliveryFrom": DELIVERY_FROM.isoformat(),
        "deliveryTo": DELIVERY_TO.isoformat(),
        "actuals": actuals,
        "forecasts": forecasts,
        "duplicateActualIntervals": quality["duplicateActualIntervals"],
        "duplicateActualConflicts": quality["duplicateActualConflicts"],
        "duplicateForecastIntervals": sum(1 for row in forecasts if row.get("duplicate")),
        "duplicateForecastConflicts": sum(1 for row in forecasts if row.get("duplicateConflict")),
        "emptyExtract": not actuals and not forecasts,
    }


def expected_january_actuals() -> set[str]:
    return {canonical(moment) for day in delivery_dates() for moment in half_hours(day)}


def expected_january_forecast_hours() -> set[str]:
    return {canonical(hour_start(moment)) for day in delivery_dates() for moment in half_hours(day)}


def january_extract_problems(snapshot: dict, *, allow_empty: bool = False) -> list[str]:
    """Say why this extract must not replace the January snapshot.

    A completely empty pull is a failed extraction. Passing allow_empty
    accepts that empty pull as a deliberate empty dataset. A partial pull
    is never accepted: January needs every half-hour actual and every
    delivery hour of forecast. Conflicting FUELHH duplicates are rejected
    even when the timestamps would otherwise cover the month.
    """
    actuals = snapshot.get("actuals") or []
    forecasts = snapshot.get("forecasts") or []
    problems = []
    conflicts = snapshot.get("duplicateActualConflicts") or 0
    if conflicts:
        problems.append(
            f"{conflicts} FUELHH start times have conflicting generation values"
        )
    if not actuals and not forecasts:
        if allow_empty and not conflicts:
            return []
        problems.append("Elexon returned an empty extract, which is not a valid January snapshot")
        return problems
    actual_times = {row["startTime"] for row in actuals}
    expected_actuals = expected_january_actuals()
    if actual_times != expected_actuals:
        missing = len(expected_actuals - actual_times)
        unexpected = len(actual_times - expected_actuals)
        problems.append(
            f"actuals are incomplete (missing {missing}, unexpected {unexpected})"
        )
    forecast_hours = set()
    for row in forecasts:
        moment = try_parse_time(row.get("startTime"))
        if moment is None or not on_forecast_hour(moment):
            continue
        forecast_hours.add(canonical(hour_start(moment)))
    expected_hours = expected_january_forecast_hours()
    if forecast_hours != expected_hours:
        missing = len(expected_hours - forecast_hours)
        problems.append(f"forecasts are incomplete (missing {missing} hours)")
    return problems


def write_snapshot(snapshot: dict, path=None) -> None:
    """Replace the snapshot only after the caller has accepted the extract.

    The bytes land in a temporary file and replace the destination in one
    rename, so a crash during the write cannot leave a half-written JSON file.
    """
    path = path or default_data_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(snapshot, separators=(",", ":")))
    temporary.replace(path)


def commit_snapshot(snapshot: dict, path=None, *, allow_empty: bool = False) -> bool:
    """Validate, then atomically replace. Return False when an empty failed pull is kept out."""
    path = path or default_data_path()
    problems = january_extract_problems(snapshot, allow_empty=allow_empty)
    if problems:
        message = "Refusing to replace the snapshot: " + "; ".join(problems)
        empty_failure = not snapshot.get("actuals") and not snapshot.get("forecasts") and not allow_empty
        if empty_failure and path.exists():
            print(message, flush=True)
            return False
        raise RuntimeError(message)
    write_snapshot(snapshot, path)
    return True


def main(allow_empty: bool = False) -> None:
    with httpx.Client(headers=HEADERS, timeout=90.0, follow_redirects=True) as client:
        actual_rows = fetch_actuals(client, DELIVERY_FROM, DELIVERY_TO)
        forecast_rows = fetch_forecasts(client, PUBLISH_FROM, PUBLISH_TO)
    snapshot = build_snapshot(actual_rows, forecast_rows)
    path = default_data_path()
    if not commit_snapshot(snapshot, path, allow_empty=allow_empty):
        return
    report = build_report(snapshot["actuals"], snapshot["forecasts"])
    accuracy = report["accuracy"]
    print(
        f"Wrote {path} actuals={len(snapshot['actuals'])} "
        f"forecasts={len(snapshot['forecasts'])} "
        f"paired={accuracy['paired']}/{accuracy['expected']}",
        flush=True,
    )
    if accuracy["biasMw"] is not None:
        print(
            f"Month bias {accuracy['biasMw']:.1f} MW  "
            f"MAE {accuracy['maeMw']:.1f} MW  "
            f"energy error {accuracy['energyErrorMwh']:.1f} MWh",
            flush=True,
        )


if __name__ == "__main__":
    main()
