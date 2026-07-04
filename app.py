from flask import Flask, jsonify, redirect, request, Response
from dotenv import load_dotenv

from src.auth import auth_bp, configure_auth
from src.dashboard import dashboard_bp, request_filters
from src.db import (
    companion_payload_to_record,
    init_db,
    insert_companion_message,
    insert_message,
    insert_webhook_event,
    list_messages,
    should_store_message,
)
from src.parser import parse_whatsapp_messages
from src.query import query_bp
from src.storage import save_raw_event
from src.utils import get_env, now_iso, rows_to_csv


load_dotenv()

app = Flask(__name__)
configure_auth(app)
app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(query_bp)


@app.context_processor
def inject_runtime_context():
    return {"desktop_demo": get_env("DESKTOP_DEMO", "0") == "1"}


@app.before_request
def ensure_database():
    init_db()


@app.get("/")
def index():
    return redirect("/dashboard")


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/webhook")
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    verify_token = get_env("WHATSAPP_VERIFY_TOKEN", "")

    if mode == "subscribe" and token and token == verify_token:
        return challenge or "", 200

    return "Forbidden", 403


@app.post("/webhook")
def receive_webhook():
    payload = request.get_json(silent=True) or {}
    received_at = now_iso()
    records = [
        record
        for record in parse_whatsapp_messages(payload, raw_json_path=None)
        if should_store_message(record)
    ]

    if not records:
        insert_webhook_event(
            event_type="whatsapp_webhook_ignored",
            raw_json_path=None,
            received_at=received_at,
        )
        return jsonify({"status": "ignored", "reason": "retention_filter"}), 200

    raw_json_path = save_raw_event(payload)

    insert_webhook_event(
        event_type="whatsapp_webhook",
        raw_json_path=raw_json_path,
        received_at=received_at,
    )

    for record in records:
        record["raw_json_path"] = raw_json_path
        insert_message(record)

    return jsonify({"status": "received"}), 200


@app.post("/ingest/companion")
def ingest_companion():
    payload = request.get_json(silent=True) or {}
    if payload.get("source") != "baileys":
        return jsonify({"error": "source must be baileys"}), 400
    if not payload.get("message_id"):
        return jsonify({"error": "message_id is required"}), 400

    preview_record = companion_payload_to_record(payload)
    if not should_store_message(preview_record):
        insert_webhook_event(
            event_type="baileys_companion_ignored",
            raw_json_path=None,
            received_at=now_iso(),
        )
        return jsonify({"status": "ignored", "reason": "retention_filter"}), 200

    raw_json_path = save_raw_event(payload, source="baileys")
    payload["raw_payload_path"] = payload.get("raw_payload_path") or raw_json_path

    insert_webhook_event(
        event_type="baileys_companion_ingest",
        raw_json_path=raw_json_path,
        received_at=now_iso(),
    )
    insert_companion_message(payload)

    return jsonify({"status": "received"}), 200


@app.get("/export/messages.csv")
def export_messages_csv():
    rows = list_messages(limit=None, filters=request_filters())
    csv_text = rows_to_csv(rows)
    return Response(
        csv_text,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=messages.csv"},
    )


@app.get("/export/messages.json")
def export_messages_json():
    return jsonify({"messages": list_messages(limit=None, filters=request_filters())})


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=8000)
