from flask import Flask, render_template, request
app = Flask(__name__)


@app.route("/")
def hello_world():
    return render_template("index.html")


@app.route("/submit", methods=["POST"])
def submit():
    input_name = request.form.get("name")
    input_age = request.form.get("age")
    return render_template("hello.html", name=input_name, age=input_age)


def process_query(content):
    if content == "dinosaurs":
        return "Dinosaurs ruled the Earth 200 million years ago"
    elif content == "asteroids":
        return "Unknown"
    else:
        return "Unrecorded query, sorry"


@app.route("/query", methods=["GET"])
def query_route():
    query_param = request.args.get("q")

    if query_param:
        result = process_query(query_param)
        return result
    else:
        return "No query parameter required", 400
