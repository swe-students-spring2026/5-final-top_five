import os
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


def _run_job(req: JobRequest) -> None:
    database = db.get_db()
    try:
        db.set_job_status(database, req.job_id, "transcribing")
        segments = pipeline.transcribe_mock(req.video_path)

        db.set_job_status(database, req.job_id, "ranking")
        windows = pipeline.pack_windows(segments)
        scored = pipeline.score_windows_mock(req.prompt, windows)
        top = pipeline.select_top_n(scored, req.num_clips)

        db.set_job_status(database, req.job_id, "cutting")
        for rank, sw in enumerate(top, start=1):
            out_path = str(CLIPS_DIR / f"{req.job_id}_{rank}.mp4")
            pipeline.cut_clip_mock(req.video_path, sw.window.start, sw.window.end, out_path)
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

        db.set_job_status(database, req.job_id, "done")
    except Exception as exc:
        db.set_job_status(database, req.job_id, "failed", error=str(exc))
        raise
