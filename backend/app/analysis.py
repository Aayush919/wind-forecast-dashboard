"""Choose the pre-gate wind forecast and score it against half-hourly outturn.

WINDFOR publishes an hourly MW curve. FUELHH outturn is half-hourly. The
hourly forecast is held flat across the two half-hours that start in that
hour, which keeps energy in MWh consistent: an hourly MW value times one
hour equals the same MW on each half-hour times half an hour, summed.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone

from app.config import (
    DELIVERY_FROM,
    DELIVERY_TO,
    FUELHH_URL,
    GATE_LOCAL,
    LONDON,
    WINDFOR_URL,
)

HALF_HOUR = 0.5


def parse_time(value: str) -> datetime:
    """Parse an instant that already carries Z or an explicit numeric offset.

    A timestamp with no zone is rejected. It is not guessed as UTC, because
    that guess is wrong for a British Summer Time clock time.
    """
    text = str(value).strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp has no timezone offset: {value}")
    return parsed.astimezone(timezone.utc)


def try_parse_time(value) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return parse_time(value)
    except (TypeError, ValueError):
        return None


def on_forecast_hour(moment: datetime) -> bool:
    """True when the London clock time is exactly HH:00:00.

    WINDFOR points sit on the hour. A start one second or one minute away
    is a different interval and must not be slid onto the hour.
    """
    local = moment.astimezone(LONDON)
    return local.minute == 0 and local.second == 0 and local.microsecond == 0


def canonical(moment: datetime) -> str:
    moment = moment.astimezone(timezone.utc).replace(microsecond=0)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def as_mw(value) -> float | None:
    """Parse a generation value. Blank, text, NaN, and infinity stay missing."""
    if value is None or value == "":
        return None
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"nan", "inf", "+inf", "-inf", "infinity", "+infinity", "-infinity"}:
            return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def delivery_dates() -> list[date]:
    days = []
    day = DELIVERY_FROM
    while day <= DELIVERY_TO:
        days.append(day)
        day += timedelta(days=1)
    return days


def gate_deadline(delivery: date) -> datetime:
    """09:50 Europe/London on the morning before the settlement date."""
    local = datetime.combine(delivery - timedelta(days=1), GATE_LOCAL, tzinfo=LONDON)
    return local.astimezone(timezone.utc)


def hour_start(moment: datetime) -> datetime:
    local = moment.astimezone(LONDON).replace(minute=0, second=0, microsecond=0)
    return local.astimezone(timezone.utc)


def half_hours(delivery: date) -> list[datetime]:
    """UTC instants for one Europe/London civil day.

    The desk serves January 2026 only. That month is GMT, so each day has
    48 half-hours. The same walk follows the real civil day on a clock
    change: 46 periods when the clocks spring forward, 50 when they fall
    back. Those dates are not part of the January extract.
    """
    start = datetime.combine(delivery, datetime.min.time(), tzinfo=LONDON).astimezone(timezone.utc)
    end = datetime.combine(delivery + timedelta(days=1), datetime.min.time(), tzinfo=LONDON).astimezone(
        timezone.utc
    )
    slots = []
    cursor = start
    while cursor < end:
        slots.append(cursor)
        cursor += timedelta(minutes=30)
    return slots


def settlement_period(moment: datetime) -> int:
    """1-based position of this instant inside its London civil day."""
    local = moment.astimezone(LONDON)
    target = moment.astimezone(timezone.utc).replace(microsecond=0)
    for index, slot in enumerate(half_hours(local.date()), start=1):
        if slot.replace(microsecond=0) == target:
            return index
    return local.hour * 2 + (1 if local.minute >= 30 else 0) + 1


def collect_actuals(rows: list[dict], *, delivery_month_only: bool = False) -> tuple[list[dict], dict]:
    """Keep one generation per start time. Repeats are counted and never summed.

    The last finite value is the one that is kept. Identical repeats are a
    duplicate. Different values are a conflict. Callers that are writing the
    January snapshot refuse conflicts; the scorer still reports them.
    """
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        if row.get("fuelType") not in (None, "WIND"):
            continue
        generation = as_mw(row.get("generation"))
        start = row.get("startTime")
        if generation is None or not start:
            continue
        moment = try_parse_time(start)
        if moment is None:
            continue
        if delivery_month_only and not _in_delivery_month(moment):
            continue
        key = canonical(moment)
        grouped.setdefault(key, []).append(
            {
                "startTime": key,
                "settlementDate": row.get("settlementDate"),
                "settlementPeriod": row.get("settlementPeriod"),
                "generation": generation,
            }
        )
    cleaned = []
    duplicate_intervals = 0
    conflicts = 0
    for key in sorted(grouped):
        items = grouped[key]
        record = dict(items[-1])
        if len(items) > 1:
            duplicate_intervals += 1
            record["duplicate"] = True
            if len({item["generation"] for item in items}) > 1:
                conflicts += 1
                record["duplicateConflict"] = True
        cleaned.append(record)
    return cleaned, {
        "duplicateActualIntervals": duplicate_intervals,
        "duplicateActualConflicts": conflicts,
    }


def _in_delivery_month(moment: datetime) -> bool:
    return DELIVERY_FROM <= moment.astimezone(LONDON).date() <= DELIVERY_TO


def index_actuals(rows: list[dict]) -> dict[str, float]:
    indexed: dict[str, float] = {}
    for row in rows:
        if row.get("fuelType") not in (None, "WIND"):
            continue
        generation = as_mw(row.get("generation"))
        start = row.get("startTime")
        if generation is None or not start:
            continue
        moment = try_parse_time(start)
        if moment is None:
            continue
        indexed[canonical(moment)] = generation
    return indexed


def _forecast_tie_counts(delivery: date, rows: list[dict]) -> dict:
    """Count WINDFOR rows that share one publish time and one hourly start.

    The last finite value is the one that is scored. Identical repeats are a
    duplicate. Different megawatts are a conflicting forecast. They are never
    summed.
    """
    grouped: dict[tuple, list] = {}
    for row in rows:
        generation = as_mw(row.get("generation"))
        start = row.get("startTime")
        published = row.get("publishTime")
        if generation is None or not start or not published:
            continue
        moment = try_parse_time(start)
        published_at = try_parse_time(published)
        if moment is None or published_at is None or not on_forecast_hour(moment):
            continue
        if moment.astimezone(LONDON).date() != delivery:
            continue
        key = (canonical(hour_start(moment)), published_at)
        grouped.setdefault(key, []).append(
            (generation, bool(row.get("duplicate")), bool(row.get("duplicateConflict")))
        )
    duplicates = 0
    conflicts = 0
    for items in grouped.values():
        if len(items) > 1 or any(marked or conflict for _generation, marked, conflict in items):
            duplicates += 1
        if len({generation for generation, _marked, _conflict in items}) > 1 or any(
            conflict for _generation, _marked, conflict in items
        ):
            conflicts += 1
    return {
        "duplicateForecastIntervals": duplicates,
        "duplicateForecastConflicts": conflicts,
    }


def _settlement_mismatches(delivery: date, rows: list[dict]) -> int:
    """Count actuals whose settlement period disagrees with the interval time.

    The period shown on the desk stays the one taken from the Europe/London
    timestamp. A missing period is not a mismatch. A negative, non-numeric,
    or inconsistent period is.
    """
    found = 0
    for row in rows:
        if row.get("fuelType") not in (None, "WIND"):
            continue
        moment = try_parse_time(row.get("startTime"))
        if moment is None or moment.astimezone(LONDON).date() != delivery:
            continue
        supplied = row.get("settlementPeriod")
        if supplied is None or supplied == "":
            continue
        if isinstance(supplied, bool):
            found += 1
            continue
        if isinstance(supplied, int):
            number = supplied
        elif isinstance(supplied, str) and supplied.strip().lstrip("-").isdigit():
            number = int(supplied.strip())
        else:
            found += 1
            continue
        if number != settlement_period(moment):
            found += 1
    return found


def _note_row_quality(day: dict, delivery: date, actuals: list[dict], forecasts: list[dict]) -> None:
    day["summary"].update(_forecast_tie_counts(delivery, forecasts))
    _records, actual_quality = collect_actuals(
        [
            row
            for row in actuals
            if (moment := try_parse_time(row.get("startTime"))) is not None
            and moment.astimezone(LONDON).date() == delivery
        ]
    )
    day["summary"].update(actual_quality)
    mismatches = _settlement_mismatches(delivery, actuals)
    if mismatches:
        day["summary"]["settlementPeriodMismatches"] = mismatches


def index_forecasts(rows: list[dict]) -> dict[str, list[tuple[datetime, float]]]:
    indexed: dict[str, dict[datetime, float]] = {}
    for row in rows:
        generation = as_mw(row.get("generation"))
        start = row.get("startTime")
        published = row.get("publishTime")
        if generation is None or not start or not published:
            continue
        moment = try_parse_time(start)
        published_at = try_parse_time(published)
        if moment is None or published_at is None or not on_forecast_hour(moment):
            continue
        hour = canonical(hour_start(moment))
        indexed.setdefault(hour, {})[published_at] = generation
    return {
        hour: sorted(publishes.items())
        for hour, publishes in indexed.items()
    }


def latest_before(publishes: list[tuple[datetime, float]], gate: datetime):
    eligible = [item for item in publishes if item[0] <= gate]
    if not eligible:
        return None
    return eligible[-1]


def percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * (pct / 100)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[low]
    weight = rank - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def _stat(errors: list[float], kind: str) -> float | None:
    if not errors:
        return None
    if kind == "bias":
        return sum(errors) / len(errors)
    if kind == "mae":
        return sum(abs(error) for error in errors) / len(errors)
    if kind == "rmse":
        return math.sqrt(sum(error * error for error in errors) / len(errors))
    raise ValueError(kind)


def hourly_errors(points: list[dict]) -> list[float]:
    buckets: dict[str, list[tuple[float, float]]] = {}
    for point in points:
        if point["forecastMw"] is None or point["actualMw"] is None:
            continue
        hour = point["startTime"][:13]
        buckets.setdefault(hour, []).append((point["forecastMw"], point["actualMw"]))
    errors = []
    for pairs in buckets.values():
        forecast = sum(forecast for forecast, _ in pairs) / len(pairs)
        actual = sum(actual for _, actual in pairs) / len(pairs)
        errors.append(forecast - actual)
    return errors


def summarise(points: list[dict]) -> dict:
    """Score half-hours.

    A missing forecast or actual stays null. It is not scored as 0 MW.
    Forecast and actual energy include every present value. Bias, MAE, RMSE,
    percentiles, net energy error, and absolute energy error use only
    half-hours where both values exist.
    """
    errors = [point["errorMw"] for point in points if point["errorMw"] is not None]
    forecast_intervals = sum(point["forecastMw"] is not None for point in points)
    actual_intervals = sum(point["actualMw"] is not None for point in points)
    forecast_mwh = sum(
        point["forecastMw"] * HALF_HOUR
        for point in points
        if point["forecastMw"] is not None
    )
    actual_mwh = sum(
        point["actualMw"] * HALF_HOUR for point in points if point["actualMw"] is not None
    )
    hour_errors = hourly_errors(points)
    summary = {
        "intervals": len(points),
        "paired": len(errors),
        "forecastIntervals": forecast_intervals,
        "actualIntervals": actual_intervals,
        "missingForecastIntervals": len(points) - forecast_intervals,
        "missingActualIntervals": len(points) - actual_intervals,
        "forecastMwh": forecast_mwh,
        "actualMwh": actual_mwh,
        "energyErrorMwh": None if not errors else sum(errors) * HALF_HOUR,
        "absoluteEnergyErrorMwh": None if not errors else sum(abs(error) for error in errors) * HALF_HOUR,
        "biasMw": _stat(errors, "bias"),
        "maeMw": _stat(errors, "mae"),
        "rmseMw": _stat(errors, "rmse"),
        "hourlyPaired": len(hour_errors),
        "hourlyBiasMw": _stat(hour_errors, "bias"),
        "hourlyMaeMw": _stat(hour_errors, "mae"),
        "hourlyRmseMw": _stat(hour_errors, "rmse"),
        "p10Mw": None if not errors else percentile(errors, 10),
        "p50Mw": None if not errors else percentile(errors, 50),
        "p90Mw": None if not errors else percentile(errors, 90),
        "overForecastHalfHours": sum(1 for error in errors if error > 0),
        "underForecastHalfHours": sum(1 for error in errors if error < 0),
    }
    return summary


def build_day_indexed(
    delivery: date,
    actuals: dict[str, float],
    forecasts: dict[str, list[tuple[datetime, float]]],
) -> dict:
    gate = gate_deadline(delivery)
    points = []
    for moment in half_hours(delivery):
        start = canonical(moment)
        hour = canonical(hour_start(moment))
        chosen = latest_before(forecasts.get(hour, []), gate)
        actual = actuals.get(start)
        forecast = None if chosen is None else chosen[1]
        published = None if chosen is None else canonical(chosen[0])
        error = None if forecast is None or actual is None else forecast - actual
        points.append(
            {
                "startTime": start,
                "settlementPeriod": settlement_period(moment),
                "forecastMw": forecast,
                "actualMw": actual,
                "errorMw": error,
                "publishTime": published,
            }
        )
    vintages = {point["publishTime"] for point in points if point["publishTime"]}
    return {
        "date": delivery.isoformat(),
        "gateTime": canonical(gate),
        "forecastPublishTime": max(vintages) if vintages else None,
        "vintageCount": len(vintages),
        "summary": summarise(points),
        "points": points,
    }


def build_day(delivery: date, actuals: list[dict], forecasts: list[dict]) -> dict:
    day = build_day_indexed(delivery, index_actuals(actuals), index_forecasts(forecasts))
    _records, quality = collect_actuals(
        [
            row
            for row in actuals
            if (moment := try_parse_time(row.get("startTime"))) is not None
            and moment.astimezone(LONDON).date() == delivery
        ]
    )
    day["summary"].update(quality)
    _note_row_quality(day, delivery, actuals, forecasts)
    return day


def public_summary(day: dict) -> dict:
    return {
        "date": day["date"],
        "gateTime": day["gateTime"],
        "forecastPublishTime": day["forecastPublishTime"],
        "vintageCount": day["vintageCount"],
        **day["summary"],
    }


def _period_label(period: int) -> str:
    minutes = (period - 1) * 30
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def build_accuracy(days: list[dict]) -> dict:
    points = [point for day in days for point in day["points"]]
    grouped: dict[int, list[float]] = {}
    for point in points:
        if point["errorMw"] is None:
            continue
        grouped.setdefault(point["settlementPeriod"], []).append(point["errorMw"])
    by_period = []
    for period in range(1, 49):
        errors = grouped.get(period, [])
        by_period.append(
            {
                "settlementPeriod": period,
                "label": _period_label(period),
                "paired": len(errors),
                "biasMw": _stat(errors, "bias"),
                "maeMw": _stat(errors, "mae"),
                "rmseMw": _stat(errors, "rmse"),
            }
        )
    summary = summarise(points)
    summary["expected"] = len(points)
    summary["byDay"] = [public_summary(day) for day in days]
    summary["byPeriod"] = by_period
    return summary


def build_report(actuals: list[dict], forecasts: list[dict]) -> dict:
    actual_index = index_actuals(actuals)
    forecast_index = index_forecasts(forecasts)
    days = []
    for delivery in delivery_dates():
        day = build_day_indexed(delivery, actual_index, forecast_index)
        _note_row_quality(day, delivery, actuals, forecasts)
        days.append(day)
    return {
        "days": {day["date"]: day for day in days},
        "dayList": days,
        "accuracy": build_accuracy(days),
    }


def static_meta() -> dict:
    return {
        "product": "Day-ahead wind",
        "region": "Great Britain",
        "fuel": "WIND",
        "deliveryFrom": DELIVERY_FROM.isoformat(),
        "deliveryTo": DELIVERY_TO.isoformat(),
        "gateLocal": GATE_LOCAL.strftime("%H:%M"),
        "gateTimezone": "Europe/London",
        "gateIsAssumption": True,
        "gateRule": (
            "Business assumption, not an Elexon field: the latest WINDFOR "
            "publication at or before 09:50 Europe/London on the morning "
            "before the settlement date."
        ),
        "errorDefinition": "forecast minus actual",
        "energyErrorDefinition": (
            "(forecast MW − actual MW) × 0.5, summed over matched half-hours. "
            "Positive and negative half-hours can cancel."
        ),
        "absoluteEnergyErrorDefinition": (
            "The absolute half-hour energy errors, summed. Positive and "
            "negative errors do not cancel."
        ),
        "actualSource": "Elexon FUELHH stream, fuelType WIND",
        "forecastSource": "Elexon WINDFOR stream",
        "actualUrl": FUELHH_URL,
        "forecastUrl": WINDFOR_URL,
        "actualResolution": "Half-hourly average MW.",
        "forecastResolution": (
            "Hourly WINDFOR MW held flat across the two half-hours in that hour."
        ),
        "energyDefinition": "Average MW multiplied by 0.5 hours, summed.",
    }
