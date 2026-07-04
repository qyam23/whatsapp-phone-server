import time

from flask import Blueprint, render_template, request

from src.ai_query import AIQueryError, AIQueryNotConfigured, ai_is_configured, ask_database
from src.auth import current_username
from src.db import record_query_audit


query_bp = Blueprint("query", __name__)


@query_bp.route("/query", methods=["GET", "POST"])
def query_database():
    question = ""
    result = None
    error = None

    if request.method == "POST":
        question = request.form.get("question", "").strip()
        started = time.monotonic()
        tools_used = []
        status = "error"
        try:
            result = ask_database(question)
            tools_used = result["tools_used"]
            status = "ok"
        except AIQueryNotConfigured:
            error = "AI analysis is not configured on this server."
            status = "not_configured"
        except AIQueryError as query_error:
            error = str(query_error)
        finally:
            record_query_audit(
                username=current_username() or "unknown",
                question=question,
                tools_used=tools_used,
                status=status,
                duration_ms=(time.monotonic() - started) * 1000,
            )

    return render_template(
        "query.html",
        ai_configured=ai_is_configured(),
        question=question,
        result=result,
        error=error,
    )
