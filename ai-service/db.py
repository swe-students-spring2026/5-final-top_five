import os
from datetime import datetime
from bson import ObjectId
from pymongo import MongoClient
from pymongo.database import Database


def get_db() -> Database:
    uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/topfive")
    return MongoClient(uri)["topfive"]


def set_job_status(db: Database, job_id: str, status: str, error: str | None = None) -> None:
    update = {"status": status}
    if error is not None:
        update["error"] = error
    if status == "done":
        update["completed_at"] = datetime.utcnow()
    db.jobs.update_one({"_id": ObjectId(job_id)}, {"$set": update})


def insert_clip(
    db: Database,
    job_id: str,
    video_id: str | None,
    rank: int,
    score: float,
    start_sec: float,
    end_sec: float,
    transcript: str,
    storage_path: str,
) -> str:
    doc = {
        "job_id": ObjectId(job_id),
        "video_id": ObjectId(video_id) if video_id else None,
        "rank": rank,
        "score": score,
        "start_sec": start_sec,
        "end_sec": end_sec,
        "transcript": transcript,
        "storage_path": storage_path,
        "caption": None,
    }
    result = db.clips.insert_one(doc)
    db.jobs.update_one(
        {"_id": ObjectId(job_id)},
        {"$push": {"clip_ids": result.inserted_id}},
    )
    return str(result.inserted_id)
