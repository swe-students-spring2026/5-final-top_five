from flask import Flask, render_template, request
import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

client = MongoClient(os.getenv("MONGO_URI"))
db = client["topfive"]
app = Flask(__name__)
ALLOWED_EXTENSIONS = {"mp4", "mov", "avi", "mkv", "webm"}

def allowed_video(filename): #Ensures only videos are able to be chosen 
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        video = request.files.get("video")
        prompt = request.form.get("prompt")
        num_clips = request.form.get("num_clips")

        if not video or video.filename == "":
            return render_template("upload.html", error="Please upload a video.")

        if not allowed_video(video.filename):
            return render_template("upload.html", error="Only video files are allowed.")

        file_data = video.read()  #Temporary for now

        return render_template(
            "upload.html",
            filename=video.filename,
            prompt=prompt,
            num_clips=num_clips
        )

    return render_template("upload.html")

@app.route("/test-db")
def test_db():
    db.test.insert_one({"msg": "hello"})
    return "Inserted into DB!"

if __name__ == "__main__":
    app.run(debug=True, port=3000)


# python -m pipenv run python app.py