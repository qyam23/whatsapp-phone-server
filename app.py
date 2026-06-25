from flask import Flask, jsonify, redirect, request, Response
from dotenv import load_dotenv

from src.dashboard import dashboard_bp
from src.db import init_db, insert_message, insert_webhook_event, list_messages
from src.parser import parse_whatsapp_messages
from src.storage import save_raw_event
from src.utils import get_env, now_iso, rows_to_csv


load_dotenv()

app = Flask(__name__)
app.register_blueprint(dashboard_bp)


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
    raw_json_path = save_raw_event(payload)
    received_at = now_iso()

    insert_webhook_event(
        event_type="whatsapp_webhook",
        raw_json_path=raw_json_path,
        received_at=received_at,
    )

    for record in parse_whatsapp_messages(payload, raw_json_path):
        insert_message(record)

    return jsonify({"status": "received"}), 200


@app.get("/export/messages.csv")
def export_messages_csv():
    rows = list_messages(limit=None)
    csv_text = rows_to_csv(rows)
    return Response(
        csv_text,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=messages.csv"},
    )


@app.get("/export/messages.json")
def export_messages_json():
    return jsonify({"messages": list_messages(limit=None)})


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=8000)
