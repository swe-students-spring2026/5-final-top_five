import os
from bson import ObjectId
from datetime import datetime
from pathlib import Path
from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

import pipeline
import db

load_dotenv()

STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "./data"))
CLIPS_DIR = STORAGE_DIR / "clips"
CLIPS_DIR.mkdir(parents=True, exist_ok=True)

USE_MOCKS = os.getenv("USE_MOCKS", "true").lower() == "true"
print("USE_MOCKS =", USE_MOCKS)

app = FastAPI(title="top-five ai-service")


class JobRequest(BaseModel):
    job_id: str
    video_path: str
    prompt: str
    num_clips: int
    video_id: str | None = None


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.post("/jobs", status_code=202)
def create_job(req: JobRequest, background: BackgroundTasks):
    if req.num_clips < 1 or req.num_clips > 10:
        raise HTTPException(400, "num_clips must be between 1 and 10")
    if not req.prompt.strip():
        raise HTTPException(400, "prompt is required")

    background.add_task(_run_job, req)
    return {"job_id": req.job_id, "status": "queued"}

def clean_for_json(value):
    if isinstance(value, ObjectId):
        return str(value)

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, list):
        return [clean_for_json(item) for item in value]

    if isinstance(value, dict):
        return {key: clean_for_json(val) for key, val in value.items()}

    return value


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    database = db.get_db()

    job = database.jobs.find_one({"job_id": job_id})
    if not job:
        raise HTTPException(404, "Job not found")

    clips = list(database.clips.find({
    "$or": [
        {"job_id": job_id},
        {"job_id": ObjectId(job_id)}
    ]
}))

    return {
        "job": clean_for_json(job),
        "clips": clean_for_json(clips)
    }

def _run_job(req: JobRequest) -> None:
    import time as _time
    database = db.get_db()
    job_start = _time.time()
    print(f"\n[job {req.job_id}] Starting job for video: {req.video_path}")
    try:
        db.set_job_status(database, req.job_id, "transcribing")
        print(f"[job {req.job_id}] Status: transcribing")
        t0 = _time.time()
        transcribe = pipeline.transcribe_mock if USE_MOCKS else pipeline.transcribe_real
        segments = transcribe(req.video_path)
        print(f"[job {req.job_id}] Transcribe done in {_time.time() - t0:.1f}s, {len(segments)} segments")

        db.set_job_status(database, req.job_id, "ranking")
        print(f"[job {req.job_id}] Status: ranking")
        t0 = _time.time()
        windows = pipeline.pack_windows(segments)
        print(f"[job {req.job_id}] Packed into {len(windows)} windows")
        score = pipeline.score_windows_mock if USE_MOCKS else pipeline.score_windows_real
        scored = score(req.prompt, windows)
        print(f"[job {req.job_id}] Scoring done in {_time.time() - t0:.1f}s")
        top = pipeline.select_top_n(scored, req.num_clips)
        print(f"[job {req.job_id}] Selected top {len(top)} clips")

        db.set_job_status(database, req.job_id, "cutting")
        cut_clip = pipeline.cut_clip_mock if USE_MOCKS else pipeline.cut_clip_real
        print(f"[job {req.job_id}] Status: cutting")
        t0 = _time.time()
        for rank, sw in enumerate(top, start=1):
            out_path = str(CLIPS_DIR / f"{req.job_id}_{rank}.mp4")
            print(f"[job {req.job_id}] Cutting clip {rank}/{len(top)}...")
            cut_clip(req.video_path, sw.window.start, sw.window.end, out_path)
            db.insert_clip(
                database,
                job_id=req.job_id,
                video_id=req.video_id,
                rank=rank,
                score=sw.score,
                start_sec=sw.window.start,
                end_sec=sw.window.end,
                transcript=sw.window.text,
                storage_path=out_path,
            )
        print(f"[job {req.job_id}] Cutting done in {_time.time() - t0:.1f}s")

        db.set_job_status(database, req.job_id, "done")
        total = _time.time() - job_start
        print(f"[job {req.job_id}] ✓ DONE in {total:.1f}s total")
    except Exception as exc:
        print(f"[job {req.job_id}] ✗ FAILED: {exc}")
        db.set_job_status(database, req.job_id, "failed", error=str(exc))
        raise
