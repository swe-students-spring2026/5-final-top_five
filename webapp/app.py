from flask import Flask, render_template, request

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("file")
    if not file or file.filename == "":
        return render_template("index.html")
    file_data = file.read()  # file is in memory only rn
    return render_template("result.html", filename=file.filename)

if __name__ == "__main__":
    app.run(debug=True, port=3000)


# python -m pipenv run python app.py