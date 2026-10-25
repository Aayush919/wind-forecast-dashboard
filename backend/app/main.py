"""HTTP API for the day-ahead wind desk."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.analysis import public_summary
from app.store import SnapshotInvalid, SnapshotMissing, default_data_path, load_report


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        report = load_report()
        print(
            f"Loaded {report['accuracy']['paired']} matched half-hours",
            flush=True,
        )
    except (SnapshotMissing, SnapshotInvalid) as exc:
        print(exc, flush=True)
    yield


app = FastAPI(title="Day-ahead wind", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.exception_handler(SnapshotMissing)
def missing_snapshot(_, exc: SnapshotMissing):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(SnapshotInvalid)
def invalid_snapshot(_, exc: SnapshotInvalid):
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.get("/api/health")
def health():
    return {"status": "ok", "dataReady": default_data_path().exists()}


@app.get("/api/meta")
def meta():
    return load_report()["meta"]


@app.get("/api/days")
def days():
    report = load_report()
    return {"days": [public_summary(day) for day in report["dayList"]]}


@app.get("/api/days/{day}")
def delivery_day(day: str):
    try:
        parsed = date.fromisoformat(day)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Date must be YYYY-MM-DD") from exc
    found = load_report()["days"].get(parsed.isoformat())
    if found is None:
        raise HTTPException(status_code=404, detail="Delivery day is outside January 2026")
    return found


@app.get("/api/accuracy")
def accuracy():
    return load_report()["accuracy"]


def _attach_frontend() -> None:
    raw = os.environ.get("STATIC_DIR")
    if not raw:
        return
    static = Path(raw)
    if not (static / "index.html").is_file():
        return
    root = static.resolve()

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(root / "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        candidate = (root / full_path).resolve()
        if not candidate.is_relative_to(root):
            raise HTTPException(status_code=404)
        if candidate.is_file():
            return FileResponse(candidate)
        if full_path.startswith("api/") or full_path.startswith("assets/"):
            raise HTTPException(status_code=404)
        return FileResponse(root / "index.html")


_attach_frontend()
