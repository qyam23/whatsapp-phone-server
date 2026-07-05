from flask import Blueprint, jsonify, redirect, render_template, request, url_for

from src.db import (
    delete_machine_rule,
    delete_retention_rule,
    get_filter_options,
    get_management_dashboard,
    get_stats,
    list_machine_rules,
    list_messages,
    list_retention_rules,
    set_machine_rule_enabled,
    set_retention_rule_enabled,
    upsert_machine_rule,
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
    period = request.args.get("period", "12h")
    return render_template(
        "dashboard.html",
        dashboard=get_management_dashboard(period=period),
    )


@dashboard_bp.get("/administration")
def administration():
    filters = request_filters()
    return render_template(
        "administration.html",
        stats=get_stats(filters=filters),
        messages=list_messages(limit=50, filters=filters),
        filters=filters,
        options=get_filter_options(),
        retention_rules=list_retention_rules(),
        machine_rules=list_machine_rules(),
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


@dashboard_bp.get("/api/management")
def api_management():
    return jsonify(get_management_dashboard(period=request.args.get("period", "12h")))


@dashboard_bp.get("/api/messages")
def api_messages():
    return jsonify({"messages": list_messages(limit=100, filters=request_filters())})


@dashboard_bp.post("/retention-rules")
def add_retention_rule():
    selection = request.form.get("rule_selection", "").strip()
    if selection:
        rule_type, separator, value = selection.partition(":")
        options = get_filter_options()
        candidates = (
            [chat for chat in options["chats"] if chat["is_group"]]
            if rule_type == "chat"
            else options["senders"] if rule_type == "sender" else []
        )
        selected = next(
            (candidate for candidate in candidates if candidate["value"] == value),
            None,
        )
        if not separator or selected is None:
            return redirect(url_for("dashboard.administration"))
        label = selected["label"]
        is_group = rule_type == "chat"
    else:
        # Keep compatibility with existing form/API clients.
        rule_type = request.form.get("rule_type", "").strip()
        value = request.form.get("value", "").strip()
        label = request.form.get("label", "").strip()
        is_group = request.form.get("is_group") == "1"

    if rule_type in {"chat", "sender"} and value:
        upsert_retention_rule(rule_type, value, label=label, is_group=is_group)

    return redirect(url_for("dashboard.administration"))


@dashboard_bp.post("/retention-rules/<int:rule_id>/toggle")
def toggle_retention_rule(rule_id):
    enabled = request.form.get("enabled") == "1"
    set_retention_rule_enabled(rule_id, enabled)
    return redirect(url_for("dashboard.administration"))


@dashboard_bp.post("/retention-rules/<int:rule_id>/delete")
def remove_retention_rule(rule_id):
    delete_retention_rule(rule_id)
    return redirect(url_for("dashboard.administration"))


@dashboard_bp.post("/machine-rules")
def add_machine_rule():
    machine_name = request.form.get("machine_name", "").strip()
    pattern = request.form.get("pattern", "").strip()
    department = request.form.get("department", "").strip()
    open_keywords = request.form.get("open_keywords", "").strip()
    close_keywords = request.form.get("close_keywords", "").strip()

    if machine_name and pattern:
        upsert_machine_rule(
            machine_name=machine_name,
            pattern=pattern,
            department=department,
            open_keywords=open_keywords,
            close_keywords=close_keywords,
        )

    return redirect(url_for("dashboard.administration"))


@dashboard_bp.post("/machine-rules/<int:rule_id>/toggle")
def toggle_machine_rule(rule_id):
    set_machine_rule_enabled(rule_id, request.form.get("enabled") == "1")
    return redirect(url_for("dashboard.administration"))


@dashboard_bp.post("/machine-rules/<int:rule_id>/delete")
def remove_machine_rule(rule_id):
    delete_machine_rule(rule_id)
    return redirect(url_for("dashboard.administration"))
