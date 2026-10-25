"""Load the January snapshot and keep the scored report until the file changes."""

from __future__ import annotations

import json
import os
from pathlib import Path

from app.analysis import build_report, collect_actuals, static_meta

_cache: dict | None = None
_cache_path: str | None = None
_cache_stamp: tuple | None = None


class SnapshotMissing(Exception):
    """Raised when the ingested Elexon extract has not been written yet."""


class SnapshotInvalid(Exception):
    """Raised when the extract cannot be scored."""


def default_data_path() -> Path:
    override = os.environ.get("DATA_FILE")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / "data" / "january_2026.json"


def reset() -> None:
    global _cache, _cache_path, _cache_stamp
    _cache = None
    _cache_path = None
    _cache_stamp = None


def _snapshot_stamp(path: Path) -> tuple | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return (stat.st_mtime_ns, stat.st_size)


def read_snapshot(path: Path | None = None) -> dict:
    path = path or default_data_path()
    if not path.exists():
        raise SnapshotMissing(
            "The January snapshot is missing. From the backend directory run: python -m app.ingest"
        )
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise SnapshotInvalid("The January snapshot is not valid JSON") from exc
    actuals = payload.get("actuals") if isinstance(payload, dict) else None
    forecasts = payload.get("forecasts") if isinstance(payload, dict) else None
    if not isinstance(actuals, list) or not isinstance(forecasts, list):
        raise SnapshotInvalid("The January snapshot is missing actuals or forecasts")
    return payload


def load_report() -> dict:
    global _cache, _cache_path, _cache_stamp
    path = default_data_path()
    key = str(path)
    stamp = _snapshot_stamp(path)
    if _cache is not None and _cache_path == key and _cache_stamp == stamp:
        return _cache
    snapshot = read_snapshot(path)
    report = build_report(snapshot["actuals"], snapshot["forecasts"])
    _records, actual_quality = collect_actuals(snapshot["actuals"])
    meta = static_meta()
    meta["ingestedAt"] = snapshot.get("ingestedAt")
    meta["publishFrom"] = snapshot.get("publishFrom")
    meta["publishTo"] = snapshot.get("publishTo")
    meta["actualRows"] = len(snapshot["actuals"])
    meta["forecastRows"] = len(snapshot["forecasts"])
    meta["pairedHalfHours"] = report["accuracy"]["paired"]
    meta["duplicateActualIntervals"] = actual_quality["duplicateActualIntervals"]
    meta["duplicateActualConflicts"] = actual_quality["duplicateActualConflicts"]
    meta["duplicateForecastIntervals"] = snapshot.get("duplicateForecastIntervals", 0)
    meta["duplicateForecastConflicts"] = snapshot.get("duplicateForecastConflicts", 0)
    meta["emptyExtract"] = snapshot.get("emptyExtract", False)
    report["meta"] = meta
    _cache = report
    _cache_path = key
    _cache_stamp = stamp
    return report
