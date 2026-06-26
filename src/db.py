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
                source TEXT DEFAULT 'meta',
                chat_id TEXT,
                chat_name TEXT,
                is_group INTEGER DEFAULT 0,
                group_id TEXT,
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
                media_path TEXT,
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
        _ensure_message_columns(conn)


def _ensure_message_columns(conn):
    existing = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(messages)").fetchall()
    }
    migrations = {
        "source": "ALTER TABLE messages ADD COLUMN source TEXT DEFAULT 'meta'",
        "chat_id": "ALTER TABLE messages ADD COLUMN chat_id TEXT",
        "chat_name": "ALTER TABLE messages ADD COLUMN chat_name TEXT",
        "is_group": "ALTER TABLE messages ADD COLUMN is_group INTEGER DEFAULT 0",
        "group_id": "ALTER TABLE messages ADD COLUMN group_id TEXT",
        "media_path": "ALTER TABLE messages ADD COLUMN media_path TEXT",
    }
    for column, statement in migrations.items():
        if column not in existing:
            conn.execute(statement)


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
    record.setdefault("source", "meta")
    record.setdefault("is_group", 0)
    record.setdefault("processing_status", "new")
    record.setdefault("created_at", now_iso())

    columns = [
        "source",
        "chat_id",
        "chat_name",
        "is_group",
        "group_id",
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
        "media_path",
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


def insert_companion_message(payload):
    message_id = payload.get("message_id")
    if not message_id:
        raise ValueError("message_id is required")

    record = {
        "source": payload.get("source") or "baileys",
        "chat_id": payload.get("chat_id"),
        "chat_name": payload.get("chat_name"),
        "is_group": 1 if payload.get("is_group") else 0,
        "group_id": payload.get("group_id"),
        "whatsapp_message_id": message_id,
        "sender_phone": payload.get("sender_id"),
        "sender_name": payload.get("sender_name"),
        "timestamp": payload.get("timestamp"),
        "message_type": payload.get("message_type") or payload.get("media_type") or "unknown",
        "text_body": payload.get("text_body"),
        "media_id": payload.get("media_id"),
        "media_mime_type": payload.get("media_type"),
        "media_caption": payload.get("media_caption"),
        "media_path": payload.get("media_path"),
        "raw_json_path": payload.get("raw_payload_path"),
        "processing_status": "new",
        "created_at": now_iso(),
    }
    return insert_message(record)


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
        by_source = [
            dict(row)
            for row in conn.execute(
                """
                SELECT COALESCE(source, 'meta') AS source, COUNT(*) AS count
                FROM messages
                GROUP BY source
                ORDER BY count DESC, source ASC
                """
            ).fetchall()
        ]
        by_chat = [
            dict(row)
            for row in conn.execute(
                """
                SELECT
                    COALESCE(chat_name, chat_id, display_phone_number, 'unknown') AS chat,
                    COALESCE(chat_id, '') AS chat_id,
                    COALESCE(is_group, 0) AS is_group,
                    COUNT(*) AS count
                FROM messages
                GROUP BY chat, chat_id, is_group
                ORDER BY count DESC, chat ASC
                LIMIT 30
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
        "messages_by_source": by_source,
        "messages_by_chat": by_chat,
        "messages_by_type": by_type,
        "messages_by_sender": by_sender,
        "messages_by_day": by_day,
    }
