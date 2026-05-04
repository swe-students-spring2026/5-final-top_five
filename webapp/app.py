from flask import Flask, render_template, request
from werkzeug.utils import secure_filename
import os
from datetime import datetime
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
ALLOWED_EXTENSIONS = {"mp4", "mov", "avi", "mkv", "webm"}
UPLOAD_FOLDER = "uploads"

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
    prompt = request.form.get("prompt")
    num_clips = int(request.form.get("num_clips", 1))
    filename = request.form.get("filename")

    if not prompt:
        return render_template("upload.html", error="Please enter a prompt.")

    # Update DB with prompt info
    db.videos.update_one(
        {"filename": filename},
        {"$set": {
            "prompt": prompt,
            "num_clips": num_clips
        }}
    )

    return render_template(
    "upload.html",
    filename=filename,
    success="Clips are being generated!"
)
if __name__ == "__main__":
    app.run(debug=True, port=3000)


# python -m pipenv run python app.py