"""FastAPI server for Garmin swim FIT file parsing."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from parser import build_calendar_events, list_swim_activities, parse_swim_fit
from workout_export import build_workout_fit_bytes
from db import init_db

app = FastAPI(title="Garmin Swim Parser")


@app.on_event("startup")
def on_startup() -> None:
    init_db()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

APP_ROOT = Path(__file__).parent.parent.resolve()
DATA_DIR = Path(os.environ.get("GARMIN_DATA_DIR", str(APP_ROOT))).resolve()
STATIC_DIR = APP_ROOT / "frontend" / "dist"


def _safe_fit_path(filename: str) -> Path:
    if not filename or filename != Path(filename).name:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not filename.lower().endswith(".fit"):
        raise HTTPException(status_code=400, detail="Only .fit files are supported")

    path = (DATA_DIR / filename).resolve()
    try:
        path.relative_to(DATA_DIR)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid file path") from exc

    if not path.exists():
        raise HTTPException(status_code=404, detail="FIT file not found")
    return path


def _dated_filename(original_name: str, activity_start: str | None) -> str:
    """Build filename with YYYYMMDD from activity start time to avoid overwrites."""
    stem = Path(original_name).stem
    if activity_start:
        date_str = activity_start[:10].replace("-", "")
    else:
        date_str = datetime.now().strftime("%Y%m%d")

    candidate = f"{stem}_{date_str}.fit"
    dest = DATA_DIR / candidate
    if not dest.exists():
        return candidate

    suffix = 2
    while True:
        candidate = f"{stem}_{date_str}_{suffix}.fit"
        if not (DATA_DIR / candidate).exists():
            return candidate
        suffix += 1


@app.get("/api/health")
def health():
    return {"status": "ok", "data_dir": str(DATA_DIR)}


@app.get("/api/activities")
def get_activities():
    activities = list_swim_activities(DATA_DIR)
    return {
        "directory": str(DATA_DIR),
        "count": len(activities),
        "activities": activities,
    }


@app.get("/api/activities/{filename}")
def get_activity(filename: str):
    path = _safe_fit_path(filename)
    try:
        data = parse_swim_fit(path)
        data["filename"] = path.name
        return data
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/activity")
def get_default_activity():
    activities = list_swim_activities(DATA_DIR)
    valid = [item for item in activities if not item.get("error")]
    if not valid:
        raise HTTPException(status_code=404, detail="No FIT files found in data directory")
    return get_activity(valid[0]["filename"])


@app.get("/api/calendar")
def get_calendar(year: Optional[int] = None, month: Optional[int] = None):
    events = build_calendar_events(DATA_DIR)
    if year is not None and month is not None:
        prefix = f"{year:04d}-{month:02d}"
        events = [event for event in events if event.get("date", "").startswith(prefix)]
    return {
        "count": len(events),
        "events": events,
    }


@app.get("/api/activities/{filename}/training-plan.fit")
def download_training_plan(filename: str):
    path = _safe_fit_path(filename)
    try:
        data = parse_swim_fit(path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    plan = (data.get("training_analysis") or {}).get("next_plan")
    if not plan:
        raise HTTPException(status_code=404, detail="该活动没有可用的训练计划")

    try:
        fit_bytes, download_name = build_workout_fit_bytes(plan)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return Response(
        content=fit_bytes,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{download_name}"'},
    )


@app.post("/api/activity/upload")
async def upload_activity(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".fit"):
        raise HTTPException(status_code=400, detail="Please upload a .fit file")

    original_name = Path(file.filename).name
    tmp_path = DATA_DIR / f".upload_{original_name}"
    content = await file.read()
    tmp_path.write_bytes(content)

    try:
        data = parse_swim_fit(tmp_path)
        saved_name = _dated_filename(original_name, data.get("summary", {}).get("start_time"))
        dest = DATA_DIR / saved_name
        tmp_path.replace(dest)
        data["filename"] = saved_name
        data["original_filename"] = original_name
        return data
    except Exception as exc:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="frontend")
