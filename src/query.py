import time

from flask import Blueprint, jsonify, render_template, request

from src.ai_query import AIQueryError, AIQueryNotConfigured, ai_is_configured, ask_database
from src.auth import ai_login_required, current_username
from src.db import record_query_audit


query_bp = Blueprint("query", __name__)


def _run_query(question):
    started = time.monotonic()
    tools_used = []
    status = "error"
    try:
        result = ask_database(question)
        tools_used = result["tools_used"]
        status = "ok"
        return result, None
    except AIQueryNotConfigured:
        status = "not_configured"
        return None, "AI analysis is not configured on this server."
    except AIQueryError as query_error:
        return None, str(query_error)
    finally:
        record_query_audit(
            username=current_username() or "unknown",
            question=question,
            tools_used=tools_used,
            status=status,
            duration_ms=(time.monotonic() - started) * 1000,
        )


@query_bp.route("/query", methods=["GET", "POST"])
@ai_login_required
def query_database():
    question = ""
    result = None
    error = None

    if request.method == "POST":
        question = request.form.get("question", "").strip()
        result, error = _run_query(question)

    return render_template(
        "query.html",
        ai_configured=ai_is_configured(),
        question=question,
        result=result,
        error=error,
    )


@query_bp.post("/api/ai/query")
@ai_login_required(api=True)
def query_api():
    payload = request.get_json(silent=True) or {}
    question = str(payload.get("question", "")).strip()
    result, error = _run_query(question)
    if error:
        status_code = 503 if not ai_is_configured() else 400
        return jsonify({"error": error}), status_code
    return jsonify(result)
