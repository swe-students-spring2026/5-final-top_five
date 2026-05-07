from flask import Flask, render_template, request, redirect, url_for, Response
from werkzeug.utils import secure_filename
import os
import tempfile
from datetime import datetime, timezone
from bson import ObjectId
import requests
from pymongo import MongoClient
from gridfs import GridFSBucket
from dotenv import load_dotenv

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
REPO_DIR = BASE_DIR.parent

# Load env vars from common project locations.
load_dotenv(REPO_DIR / ".env")
load_dotenv(BASE_DIR / ".env")
load_dotenv(REPO_DIR / "ai-service" / ".env")

app = Flask(__name__)
ALLOWED_EXTENSIONS = {"mp4", "mov", "avi", "mkv", "webm"}
UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "/tmp/uploads")
AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://localhost:8000")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

client = MongoClient(
    os.getenv("MONGO_URI", "mongodb://localhost:27017/topfive"),
    serverSelectionTimeoutMS=5000,
)
db = client["topfive"]
videos_bucket = GridFSBucket(db, bucket_name="videos")
clips_grid = GridFSBucket(db, bucket_name="clips_grid")


def to_json_safe(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [to_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {k: to_json_safe(v) for k, v in value.items()}
    return value


def allowed_video(filename): #Ensures only videos are able to be chosen 
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/test-db")
def test_db():
    db.test.insert_one({"msg": "hello"})
    return "inserted into DB!"

@app.route("/upload-video", methods=["POST"])
def upload_video():
    video = request.files.get("video")

    if not video or video.filename == "":
        return render_template("index.html", error="Please upload a video.")

    if not allowed_video(video.filename):
        return render_template("index.html", error="Only video files are allowed.")

    filename = secure_filename(video.filename)

    try:
        gridfs_id = videos_bucket.upload_from_stream(filename, video.stream)
        db.videos.insert_one({
            "filename": filename,
            "gridfs_id": gridfs_id,
            "uploaded_at": datetime.utcnow()
        })
    except Exception as exc:
        return render_template(
            "index.html",
            error=f"Database connection failed. Check MONGO_URI. ({exc})",
        ), 500

    return render_template("upload.html", filename=filename, video_id=str(gridfs_id))

@app.route("/generate-clips", methods=["POST"])
def generate_clips():
    prompt = (request.form.get("prompt") or "").strip()
    num_clips = int(request.form.get("num_clips", 1))
    filename = request.form.get("filename")

    if not prompt:
        return render_template("upload.html", filename=filename, error="Please enter a prompt.")

    video_id = request.form.get("video_id")
    video = db.videos.find_one({"gridfs_id": ObjectId(video_id)}) if video_id else None
    if not video:
        return render_template("upload.html", filename=filename, error="Video not found. Please upload again.")

    job_result = db.jobs.insert_one({
        "video_id": video["_id"],
        "prompt": prompt,
        "num_clips": num_clips,
        "status": "queued",
        "error": None,
        "created_at": datetime.now(timezone.utc),
        "completed_at": None,
        "clip_ids": [],
    })

    job_id = str(job_result.inserted_id)

    try:
        suffix = os.path.splitext(filename)[1] or ".mp4"
        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        stream = videos_bucket.open_download_stream(ObjectId(video_id))
        tmp.write(stream.read())
        tmp.close()

        resp = requests.post(
            f"{AI_SERVICE_URL}/jobs",
            json={
                "job_id": job_id,
                "video_id": str(video["_id"]),
                "video_path": tmp.name,
                "prompt": prompt,
                "num_clips": num_clips,
            },
            timeout=5,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        db.jobs.update_one(
            {"_id": job_result.inserted_id},
            {"$set": {"status": "failed", "error": f"ai-service unreachable: {exc}"}},
        )

    return redirect(url_for("job_status", job_id=str(job_id)))


@app.route("/jobs/<job_id>")
def job_status(job_id):
    try:
        oid = ObjectId(job_id)
    except Exception:
        return render_template("job.html", error="Invalid job id."), 404

    job = db.jobs.find_one({"_id": oid})
    if not job:
        return render_template("job.html", error="Job not found."), 404

    clips = []
    if job["status"] == "done":
        clips = list(db.clips.find({
            "$or": [{"job_id": job_id}, {"job_id": oid}]
        }).sort("rank", 1))

        for clip in clips:
            if not clip.get("clips_grid_id"):
                storage_path = clip.get("storage_path", "")
                if not os.path.isabs(storage_path):
                    ai_dir = REPO_DIR / "ai-service"
                    storage_path = str(ai_dir / storage_path)
                if os.path.exists(storage_path):
                    with open(storage_path, "rb") as f:
                        gid = clips_grid.upload_from_stream(
                            os.path.basename(storage_path), f,
                            metadata={"job_id": job_id, "rank": clip.get("rank")}
                        )
                    db.clips.update_one({"_id": clip["_id"]}, {"$set": {"clips_grid_id": gid}})
                    clip["clips_grid_id"] = gid

    return render_template("job.html", job=job, clips=clips, job_id=job_id)

@app.route("/jobs-api/<job_id>")
def job_status_api(job_id):
    """JSON API endpoint for progress polling."""
    try:
        oid = ObjectId(job_id)
    except Exception:
        return {"error": "Invalid job id."}, 404
    
    job = db.jobs.find_one({"_id": oid})
    if not job:
        return {"error": "Job not found."}, 404
    
    job_data = to_json_safe(job)
    
    return {"job": job_data}, 200

@app.route("/video/<video_id>")
def serve_video(video_id):
    stream = videos_bucket.open_download_stream(ObjectId(video_id))
    return Response(stream, mimetype="video/mp4")


@app.route("/clip-video/<gridfs_id>")
def serve_clip(gridfs_id):
    stream = clips_grid.open_download_stream(ObjectId(gridfs_id))
    return Response(stream, mimetype="video/mp4")


@app.route("/history")
def history():
    jobs = list(db.jobs.find().sort("created_at", -1).limit(20))
    video_ids = {j["video_id"] for j in jobs if j.get("video_id")}
    videos_by_id = {v["_id"]: v for v in db.videos.find({"_id": {"$in": list(video_ids)}})}
    for job in jobs:
        video = videos_by_id.get(job.get("video_id"))
        job["filename"] = video["filename"] if video else "(unknown)"
    return render_template("history.html", jobs=jobs)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port, debug=False)


# python -m pipenv run python app.py