# app.py
import os
import re
from uuid import uuid4
from dotenv import load_dotenv

load_dotenv()

import sqlparse
from flask import Flask, abort, jsonify, render_template, request, send_from_directory, session
from flask_cors import CORS

from main import GENERATED_DIR, process_question
from voice_groq import VoiceConfigError, load_speech_models, synthesize_speech, transcribe_audio

app = Flask(__name__)


app.secret_key = os.getenv("FLASK_SECRET")

CORS(app, resources={r"/*": {"origins": "*"}})


def format_sql(sql):
    return sqlparse.format(sql, reindent=True, keyword_case="upper")


MAX_CONTEXT_LENGTH = 3  # Number of previous exchanges to keep
MAX_STORED_ANSWER = 1500
PDF_NAME = re.compile(r"^[0-9a-f]{32}\.pdf$")


def plain_text_answer(result) -> str:
    """Store a short plain-text answer so the session cookie stays small."""
    if not result:
        return ""
    parts = []
    for item in result:
        text = re.sub(r"<[^>]+>", " ", str(item))
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            parts.append(text)
    combined = "\n".join(parts)
    if len(combined) > MAX_STORED_ANSWER:
        return combined[:MAX_STORED_ANSWER] + "..."
    return combined


def result_includes_map(result) -> bool:
    if not result:
        return False
    for item in result:
        text = str(item)
        if 'id="map"' in text or "id='map'" in text or "initMap" in text:
            return True
    return False


def get_conversation_history():
    if "conversation_history" not in session:
        session["conversation_history"] = []
    return session["conversation_history"]


def add_to_conversation_history(question, answer):
    history = get_conversation_history()
    history.append({"question": question, "answer": answer})
    if len(history) > MAX_CONTEXT_LENGTH:
        history.pop(0)
    session["conversation_history"] = history


@app.route("/downloads/<filename>")
def download_pdf(filename):
    safe_name = os.path.basename(filename)
    if safe_name != filename or not PDF_NAME.fullmatch(safe_name):
        abort(404)
    directory = os.path.abspath(GENERATED_DIR)
    file_path = os.path.abspath(os.path.join(directory, safe_name))
    if os.path.commonpath([directory, file_path]) != directory or not os.path.isfile(file_path):
        abort(404)
    return send_from_directory(directory, safe_name, as_attachment=True)


@app.route("/voice/transcribe", methods=["POST"])
def voice_transcribe():
    audio = request.files.get("audio")
    if audio is None:
        return jsonify(error="Record a short question and try again."), 400
    payload = audio.read()
    if not payload:
        return jsonify(error="Record a short question and try again."), 400
    try:
        text = transcribe_audio(payload, audio.filename or "audio.wav", audio.mimetype or "audio/wav")
    except VoiceConfigError as exc:
        return jsonify(error=str(exc)), 503
    return jsonify(text=text)


@app.route("/voice/speak", methods=["POST"])
def voice_speak():
    payload = request.get_json(silent=True) or {}
    text = payload.get("text") if isinstance(payload, dict) else ""
    if not str(text or "").strip():
        return jsonify(error="Nothing to speak."), 400
    try:
        audio = synthesize_speech(str(text))
    except VoiceConfigError as exc:
        return jsonify(error=str(exc)), 503
    return audio, 200, {"Content-Type": "audio/wav"}


@app.route("/", methods=["GET", "POST"])
def index():
    result = None
    formatted_query = None
    if "user_id" not in session:
        session["user_id"] = str(uuid4())
    prior_history = list(get_conversation_history())
    if request.method == "POST":
        if request.form.get("sign_out", None):
            session.clear()
            return render_template(
                "index.html",
                result=None,
                query=formatted_query,
                conversation_history=[],
                include_map=False,
                gmaps_api_key=os.getenv("GPLACES_API_KEY"),
            )
        question = request.form["question"]
        result = process_question(question, prior_history)
        add_to_conversation_history(question, plain_text_answer(result))

    return render_template(
        "index.html",
        gmaps_api_key=os.getenv("GPLACES_API_KEY"),
        result=result,
        query=formatted_query,
        conversation_history=prior_history,
        include_map=result_includes_map(result),
    )


if __name__ == "__main__":
    try:
        load_speech_models()
    except VoiceConfigError as exc:
        print(exc)
    app.run(debug=True)
