"""Flask UI + JSON API for Condo GPT."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from flask import Flask, jsonify, render_template, request, session
from flask_cors import CORS

from condo_gpt.runtime import approve_agent, process_question, run_agent
from condo_gpt.config import get_settings
from condo_gpt.memory import append_turn_pair
from condo_gpt.observability import configure_tracing
from condo_gpt.security.audit import check_api_key

configure_tracing()
settings = get_settings()

_APP_DIR = Path(__file__).resolve().parent
app = Flask(
    __name__,
    template_folder=str(_APP_DIR / "templates"),
    static_folder=str(_APP_DIR / "static"),
)
app.secret_key = settings.flask_secret or os.urandom(24).hex()
CORS(app, resources={r"/api/*": {"origins": settings.cors_origins}})

try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address

    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=[],
        storage_uri="memory://",
    )
except ImportError:
    limiter = None


def _session_cost() -> float:
    return float(session.get("session_cost_usd", 0.0))


def _add_session_cost(amount: float) -> None:
    session["session_cost_usd"] = _session_cost() + (amount or 0.0)
    session.modified = True


def _require_api_key():
    """API key check for /api/* — web form POST / is exempt."""
    if not settings.api_auth_enabled:
        return None
    key = request.headers.get("X-API-Key")
    if not check_api_key(key):
        return jsonify({"error": "Unauthorized — provide X-API-Key header"}), 401
    return None


@app.before_request
def _api_auth_middleware():
    if request.path.startswith("/api/") and request.path != "/api/health":
        return _require_api_key()


def get_conversation_history():
    if "conversation_history" not in session:
        session["conversation_history"] = []
    return session["conversation_history"]


@app.route("/", methods=["GET", "POST"])
def index():
    result = None
    response_obj = None
    if "user_id" not in session:
        session["user_id"] = str(uuid4())
    run_id = None
    if request.method == "POST":
        if request.form.get("sign_out", None):
            session.clear()
            return render_template(
                "index.html",
                result=None,
                conversation_history=[],
                run_id=None,
                response=None,
                gmaps_api_key=settings.gplaces_api_key,
                api_key_required=settings.api_auth_enabled,
            )
        if request.form.get("approve_run_id"):
            response_obj = approve_agent(
                request.form["approve_run_id"],
                approved=request.form.get("approve_action") == "approve",
                owner_id=session.get("user_id"),
            )
            run_id = response_obj.run_id
            result = response_obj.display_blocks()
            _add_session_cost(response_obj.est_cost_usd or 0.0)
        else:
            question = request.form["question"]
            conversation_history = get_conversation_history()
            response_obj = run_agent(
                question,
                conversation_history,
                metadata={"user_id": session.get("user_id"), "channel": "web"},
                session_cost_usd=_session_cost(),
            )
            run_id = response_obj.run_id
            _add_session_cost(response_obj.est_cost_usd or 0.0)
            if response_obj.error and response_obj.status == "error":
                result = [f"Error: {response_obj.error}"]
            else:
                result = response_obj.display_blocks()
            if response_obj.status == "completed":
                session["conversation_history"] = append_turn_pair(
                    conversation_history,
                    question,
                    response_obj.text or "",
                    artifacts=[a.model_dump() for a in response_obj.artifacts],
                    sql_citations=[c.model_dump() for c in response_obj.sql_citations],
                )
                session.modified = True

    return render_template(
        "index.html",
        gmaps_api_key=settings.gplaces_api_key,
        result=result,
        conversation_history=session.get("conversation_history", []),
        run_id=run_id,
        response=response_obj,
        prompt_version=settings.prompt_version,
        api_key_required=settings.api_auth_enabled,
        session_cost=_session_cost(),
        max_session_cost=settings.max_session_cost_usd,
    )


def _chat_rate_limit():
    if limiter:
        return limiter.limit(settings.rate_limit)
    return lambda f: f


@app.route("/api/chat", methods=["POST"])
@_chat_rate_limit()
def api_chat():
    """Typed JSON API used by evals and external clients."""
    payload = request.get_json(force=True, silent=True) or {}
    question = payload.get("question") or payload.get("message")
    if not question:
        return jsonify({"error": "question is required"}), 400
    history = payload.get("conversation_history") or payload.get("history") or []
    session_cost = float(payload.get("session_cost_usd", 0.0))
    response = run_agent(
        question,
        history,
        metadata={
            "channel": "api",
            "eval_case_id": payload.get("eval_case_id"),
            "user_id": payload.get("user_id"),
        },
        session_cost_usd=session_cost,
    )
    return jsonify(response.model_dump())


@app.route("/api/chat/approve", methods=["POST"])
@_chat_rate_limit()
def api_chat_approve():
    payload = request.get_json(force=True, silent=True) or {}
    run_id = payload.get("run_id")
    if not run_id:
        return jsonify({"error": "run_id is required"}), 400
    approved = payload.get("approved", True)
    response = approve_agent(
        run_id,
        approved=bool(approved),
        owner_id=payload.get("user_id"),
    )
    return jsonify(response.model_dump())


@app.get("/api/health")
def health():
    return jsonify(
        {
            "ok": True,
            "prompt_version": settings.prompt_version,
            "llm_provider": settings.llm_provider,
            "model": settings.model,
            "model_hard": settings.model_hard,
            "tracing": settings.langchain_tracing,
            "api_auth": settings.api_auth_enabled,
        }
    )


if __name__ == "__main__":
    app.run(debug=settings.flask_debug, port=int(os.getenv("PORT", "5000")))
