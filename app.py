"""Flask web application for PDF batch renaming."""

import os
from flask import Flask, jsonify, request, render_template

import renamer

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/scan", methods=["POST"])
def scan():
    data = request.get_json(force=True)
    directory = data.get("directory", "")
    if not directory:
        return jsonify({"error": "No directory specified"}), 400
    if not os.path.isdir(directory):
        return jsonify({"error": f"Directory not found: {directory}"}), 404
    template = data.get("template")
    result = renamer.scan_directory(directory, template=template)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@app.route("/execute", methods=["POST"])
def execute():
    data = request.get_json(force=True)
    files = data.get("files", [])
    session_id = data.get("session_id")
    if not files:
        return jsonify({"error": "No files specified"}), 400
    result = renamer.execute_renames(files, session_id)
    return jsonify(result)


@app.route("/undo", methods=["POST"])
def undo():
    data = request.get_json(force=True)
    index = data.get("index")
    session_id = data.get("session_id")

    if index is not None:
        result = renamer.undo_single(int(index))
    elif session_id:
        result = renamer.undo_session(session_id)
    else:
        return jsonify({"error": "Provide 'index' or 'session_id'"}), 400

    return jsonify(result)


@app.route("/history", methods=["GET"])
def history():
    return jsonify(renamer.get_history())


@app.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "GET":
        return jsonify(renamer.load_settings())
    data = request.get_json(force=True)
    updated = renamer.save_settings(data)
    return jsonify(updated)


@app.route("/templates", methods=["GET"])
def templates():
    return jsonify(renamer.TEMPLATE_PRESETS)


if __name__ == "__main__":
    app.run(
        debug=os.environ.get("FLASK_DEBUG", "0") == "1",
        host=os.environ.get("FLASK_HOST", "127.0.0.1"),
        port=int(os.environ.get("FLASK_PORT", "5000")),
    )
