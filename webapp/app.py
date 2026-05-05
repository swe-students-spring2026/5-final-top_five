from flask import Flask, render_template, request, redirect, url_for
from werkzeug.utils import secure_filename
import os
from datetime import datetime
from bson import ObjectId
import requests
from pymongo import MongoClient
from dotenv import load_dotenv
from flask import send_from_directory

load_dotenv()

app = Flask(__name__)
ALLOWED_EXTENSIONS = {"mp4", "mov", "avi", "mkv", "webm"}
UPLOAD_FOLDER = "uploads"
AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://localhost:8000")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017/topfive"))
db = client["topfive"]


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
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    video.save(filepath)

    db.videos.insert_one({
        "filename": filename,
        "filepath": filepath,
        "uploaded_at": datetime.utcnow()
    })

    return render_template("upload.html", filename=filename)

@app.route("/generate-clips", methods=["POST"])
def generate_clips():
    prompt = (request.form.get("prompt") or "").strip()
    num_clips = int(request.form.get("num_clips", 1))
    filename = request.form.get("filename")

    if not prompt:
        return render_template("upload.html", filename=filename, error="Please enter a prompt.")

    video = db.videos.find_one({"filename": filename})
    if not video:
        return render_template("upload.html", filename=filename, error="Video not found. Please upload again.")

    job_result = db.jobs.insert_one({
        "video_id": video["_id"],
        "prompt": prompt,
        "num_clips": num_clips,
        "status": "queued",
        "error": None,
        "created_at": datetime.utcnow(),
        "completed_at": None,
        "clip_ids": [],
    })

    job_id = str(job_result.inserted_id)

    db.jobs.update_one(
        {"_id": job_result.inserted_id},
        {"$set": {"job_id": job_id}}
    )
    print("Sending job_id:", str(job_id))
    print("Sending video_path:", os.path.abspath(video["filepath"]))

    try:
        resp = requests.post(
            f"{AI_SERVICE_URL}/jobs",
            json={
                "job_id": job_id,
                "video_id": str(video["_id"]),
                "video_path": os.path.abspath(video["filepath"]),
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

    clips = list(db.clips.find({
        "$or": [
            {"job_id": job_id},
            {"job_id": oid}
        ]
    }).sort("rank", 1)) if job["status"] == "done" else []

    return render_template("job.html", job=job, clips=clips, job_id=job_id)

@app.route("/clips/<filename>")
def serve_clip(filename):
    return send_from_directory("../ai-service/data/clips", filename)


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
    app.run(debug=True, port=3000)


# python -m pipenv run python app.py