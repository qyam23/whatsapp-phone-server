from flask import Blueprint, jsonify, render_template

from src.db import get_stats, list_messages


dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.get("/dashboard")
def dashboard():
    stats = get_stats()
    messages = list_messages(limit=50)
    return render_template("dashboard.html", stats=stats, messages=messages)


@dashboard_bp.get("/messages")
def messages_page():
    messages = list_messages(limit=100)
    return render_template("messages.html", messages=messages)


@dashboard_bp.get("/api/stats")
def api_stats():
    return jsonify(get_stats())


@dashboard_bp.get("/api/messages")
def api_messages():
    return jsonify({"messages": list_messages(limit=100)})
