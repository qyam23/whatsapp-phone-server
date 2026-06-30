from flask import Blueprint, jsonify, redirect, render_template, request, url_for

from src.db import (
    delete_retention_rule,
    get_filter_options,
    get_stats,
    list_messages,
    list_retention_rules,
    set_retention_rule_enabled,
    upsert_retention_rule,
)


dashboard_bp = Blueprint("dashboard", __name__)


def request_filters(args=None):
    args = args or request.args
    filters = {
        "source": args.get("source", "").strip(),
        "message_type": args.get("message_type", "").strip(),
        "chat": args.get("chat", "").strip(),
        "sender": args.get("sender", "").strip(),
        "kind": args.get("kind", "").strip(),
        "date_from": args.get("date_from", "").strip(),
        "date_to": args.get("date_to", "").strip(),
        "q": args.get("q", "").strip(),
    }
    return {key: value for key, value in filters.items() if value}


@dashboard_bp.get("/dashboard")
def dashboard():
    filters = request_filters()
    stats = get_stats(filters=filters)
    messages = list_messages(limit=50, filters=filters)
    return render_template(
        "dashboard.html",
        stats=stats,
        messages=messages,
        filters=filters,
        options=get_filter_options(),
        retention_rules=list_retention_rules(),
    )


@dashboard_bp.get("/messages")
def messages_page():
    filters = request_filters()
    messages = list_messages(limit=100, filters=filters)
    return render_template(
        "messages.html",
        messages=messages,
        filters=filters,
        options=get_filter_options(),
    )


@dashboard_bp.get("/api/stats")
def api_stats():
    return jsonify(get_stats(filters=request_filters()))


@dashboard_bp.get("/api/messages")
def api_messages():
    return jsonify({"messages": list_messages(limit=100, filters=request_filters())})


@dashboard_bp.post("/retention-rules")
def add_retention_rule():
    rule_type = request.form.get("rule_type", "").strip()
    value = request.form.get("value", "").strip()
    label = request.form.get("label", "").strip()
    is_group = request.form.get("is_group") == "1"

    if rule_type in {"chat", "sender"} and value:
        upsert_retention_rule(rule_type, value, label=label, is_group=is_group)

    return redirect(url_for("dashboard.dashboard"))


@dashboard_bp.post("/retention-rules/<int:rule_id>/toggle")
def toggle_retention_rule(rule_id):
    enabled = request.form.get("enabled") == "1"
    set_retention_rule_enabled(rule_id, enabled)
    return redirect(url_for("dashboard.dashboard"))


@dashboard_bp.post("/retention-rules/<int:rule_id>/delete")
def remove_retention_rule(rule_id):
    delete_retention_rule(rule_id)
    return redirect(url_for("dashboard.dashboard"))
