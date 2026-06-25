import sqlite3
from pathlib import Path

from src.utils import now_iso


DB_PATH = Path("data") / "messages.db"


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                whatsapp_message_id TEXT UNIQUE,
                wa_business_phone_number_id TEXT,
                display_phone_number TEXT,
                sender_phone TEXT,
                sender_name TEXT,
                timestamp TEXT,
                message_type TEXT,
                text_body TEXT,
                media_id TEXT,
                media_mime_type TEXT,
                media_sha256 TEXT,
                media_filename TEXT,
                media_caption TEXT,
                raw_json_path TEXT,
                processing_status TEXT DEFAULT 'new',
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS webhook_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT,
                raw_json_path TEXT,
                received_at TEXT
            );

            CREATE TABLE IF NOT EXISTS media_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER,
                media_id TEXT,
                local_path TEXT,
                drive_file_id TEXT,
                drive_link TEXT,
                mime_type TEXT,
                file_size INTEGER,
                sha256_hash TEXT,
                upload_status TEXT DEFAULT 'pending',
                created_at TEXT,
                FOREIGN KEY(message_id) REFERENCES messages(id)
            );
            """
        )


def insert_webhook_event(event_type, raw_json_path, received_at):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO webhook_events (event_type, raw_json_path, received_at)
            VALUES (?, ?, ?)
            """,
            (event_type, raw_json_path, received_at),
        )


def insert_message(record):
    record = dict(record)
    record.setdefault("processing_status", "new")
    record.setdefault("created_at", now_iso())

    columns = [
        "whatsapp_message_id",
        "wa_business_phone_number_id",
        "display_phone_number",
        "sender_phone",
        "sender_name",
        "timestamp",
        "message_type",
        "text_body",
        "media_id",
        "media_mime_type",
        "media_sha256",
        "media_filename",
        "media_caption",
        "raw_json_path",
        "processing_status",
        "created_at",
    ]
    values = [record.get(column) for column in columns]

    with get_connection() as conn:
        cursor = conn.execute(
            f"""
            INSERT OR IGNORE INTO messages ({", ".join(columns)})
            VALUES ({", ".join(["?"] * len(columns))})
            """,
            values,
        )
        return cursor.lastrowid


def list_messages(limit=20):
    query = "SELECT * FROM messages ORDER BY COALESCE(timestamp, created_at) DESC, id DESC"
    params = []
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)

    with get_connection() as conn:
        return [dict(row) for row in conn.execute(query, params).fetchall()]


def get_stats():
    with get_connection() as conn:
        total_messages = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        messages_today = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE date(created_at) = date('now')"
        ).fetchone()[0]
        last_webhook = conn.execute(
            "SELECT received_at FROM webhook_events ORDER BY id DESC LIMIT 1"
        ).fetchone()
        last_message = conn.execute(
            "SELECT COALESCE(timestamp, created_at) AS received FROM messages ORDER BY id DESC LIMIT 1"
        ).fetchone()

        by_type = [
            dict(row)
            for row in conn.execute(
                """
                SELECT message_type, COUNT(*) AS count
                FROM messages
                GROUP BY message_type
                ORDER BY count DESC, message_type ASC
                """
            ).fetchall()
        ]
        by_sender = [
            dict(row)
            for row in conn.execute(
                """
                SELECT COALESCE(sender_name, sender_phone, 'unknown') AS sender, COUNT(*) AS count
                FROM messages
                GROUP BY sender
                ORDER BY count DESC, sender ASC
                LIMIT 20
                """
            ).fetchall()
        ]
        by_day = [
            dict(row)
            for row in conn.execute(
                """
                SELECT date(COALESCE(timestamp, created_at)) AS day, COUNT(*) AS count
                FROM messages
                GROUP BY day
                ORDER BY day DESC
                LIMIT 30
                """
            ).fetchall()
        ]

    type_counts = {row["message_type"] or "unknown": row["count"] for row in by_type}
    return {
        "total_messages": total_messages,
        "messages_today": messages_today,
        "text_count": type_counts.get("text", 0),
        "image_count": type_counts.get("image", 0),
        "audio_count": type_counts.get("audio", 0),
        "video_count": type_counts.get("video", 0),
        "document_count": type_counts.get("document", 0),
        "unknown_count": type_counts.get("unknown", 0),
        "last_webhook_received_time": last_webhook["received_at"] if last_webhook else None,
        "last_message_received_time": last_message["received"] if last_message else None,
        "messages_by_type": by_type,
        "messages_by_sender": by_sender,
        "messages_by_day": by_day,
    }
