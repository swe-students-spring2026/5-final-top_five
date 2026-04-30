from flask import Flask, render_template, request

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "POST" and request.files.get("file"):
        file = request.files.get("file")
        file_data = file.read()  # file is in memory only rn
        return render_template("upload.html", filename=file.filename)

    if request.method == "POST":
        prompt = request.form.get("prompt")
        num_clips = request.form.get("num_clips")
        # AI call goes here
        return render_template("upload.html", prompt=prompt, num_clips=num_clips)

    return render_template("upload.html")

if __name__ == "__main__":
    app.run(debug=True, port=3000)


# python -m pipenv run python app.py