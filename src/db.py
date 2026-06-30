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

            CREATE TABLE IF NOT EXISTS retention_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_type TEXT NOT NULL,
                value TEXT NOT NULL,
                label TEXT,
                is_group INTEGER DEFAULT 0,
                enabled INTEGER DEFAULT 1,
                created_at TEXT,
                UNIQUE(rule_type, value)
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


def companion_payload_to_record(payload):
    message_id = payload.get("message_id")
    if not message_id:
        raise ValueError("message_id is required")

    return {
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


def insert_companion_message(payload):
    return insert_message(companion_payload_to_record(payload))


def _message_filters_where(filters=None):
    filters = filters or {}
    conditions = []
    params = []

    if filters.get("source"):
        conditions.append("COALESCE(source, 'meta') = ?")
        params.append(filters["source"])
    if filters.get("message_type"):
        conditions.append("message_type = ?")
        params.append(filters["message_type"])
    if filters.get("chat"):
        conditions.append("COALESCE(chat_id, display_phone_number, '') = ?")
        params.append(filters["chat"])
    if filters.get("sender"):
        conditions.append("COALESCE(sender_phone, sender_name, '') = ?")
        params.append(filters["sender"])
    if filters.get("kind") == "groups":
        conditions.append("COALESCE(is_group, 0) = 1")
    elif filters.get("kind") == "direct":
        conditions.append("COALESCE(is_group, 0) = 0")
    if filters.get("date_from"):
        conditions.append("date(COALESCE(timestamp, created_at)) >= date(?)")
        params.append(filters["date_from"])
    if filters.get("date_to"):
        conditions.append("date(COALESCE(timestamp, created_at)) <= date(?)")
        params.append(filters["date_to"])
    if filters.get("q"):
        conditions.append(
            """
            (
                COALESCE(text_body, '') LIKE ?
                OR COALESCE(media_caption, '') LIKE ?
                OR COALESCE(chat_name, '') LIKE ?
                OR COALESCE(sender_name, '') LIKE ?
                OR COALESCE(sender_phone, '') LIKE ?
            )
            """
        )
        like = f"%{filters['q']}%"
        params.extend([like, like, like, like, like])

    where_sql = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    return where_sql, params


def list_messages(limit=20, filters=None):
    where_sql, params = _message_filters_where(filters)
    query = f"SELECT * FROM messages{where_sql} ORDER BY COALESCE(timestamp, created_at) DESC, id DESC"
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)

    with get_connection() as conn:
        return [dict(row) for row in conn.execute(query, params).fetchall()]


def get_filter_options():
    with get_connection() as conn:
        sources = [
            row["source"]
            for row in conn.execute(
                "SELECT DISTINCT COALESCE(source, 'meta') AS source FROM messages ORDER BY source"
            ).fetchall()
            if row["source"]
        ]
        message_types = [
            row["message_type"]
            for row in conn.execute(
                "SELECT DISTINCT message_type FROM messages WHERE message_type IS NOT NULL ORDER BY message_type"
            ).fetchall()
            if row["message_type"]
        ]
        chats = [
            dict(row)
            for row in conn.execute(
                """
                SELECT
                    COALESCE(chat_id, display_phone_number, '') AS value,
                    COALESCE(chat_name, chat_id, display_phone_number, 'unknown') AS label,
                    COALESCE(is_group, 0) AS is_group,
                    COUNT(*) AS count
                FROM messages
                GROUP BY value, label, is_group
                HAVING value != ''
                ORDER BY count DESC, label ASC
                LIMIT 200
                """
            ).fetchall()
        ]
        senders = [
            dict(row)
            for row in conn.execute(
                """
                SELECT
                    COALESCE(sender_phone, sender_name, '') AS value,
                    COALESCE(sender_name, sender_phone, 'unknown') AS label,
                    COUNT(*) AS count
                FROM messages
                GROUP BY value, label
                HAVING value != ''
                ORDER BY count DESC, label ASC
                LIMIT 200
                """
            ).fetchall()
        ]

    return {
        "sources": sources,
        "message_types": message_types,
        "chats": chats,
        "senders": senders,
    }


def get_stats(filters=None):
    where_sql, params = _message_filters_where(filters)
    with get_connection() as conn:
        total_messages = conn.execute(
            f"SELECT COUNT(*) FROM messages{where_sql}", params
        ).fetchone()[0]
        messages_today = conn.execute(
            f"""
            SELECT COUNT(*) FROM messages{where_sql}
            {"AND" if where_sql else "WHERE"} date(created_at) = date('now')
            """,
            params,
        ).fetchone()[0]
        last_webhook = conn.execute(
            "SELECT received_at FROM webhook_events ORDER BY id DESC LIMIT 1"
        ).fetchone()
        last_message = conn.execute(
            f"""
            SELECT COALESCE(timestamp, created_at) AS received
            FROM messages{where_sql}
            ORDER BY id DESC
            LIMIT 1
            """,
            params,
        ).fetchone()

        by_type = [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT message_type, COUNT(*) AS count
                FROM messages{where_sql}
                GROUP BY message_type
                ORDER BY count DESC, message_type ASC
                """,
                params,
            ).fetchall()
        ]
        by_source = [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT COALESCE(source, 'meta') AS source, COUNT(*) AS count
                FROM messages{where_sql}
                GROUP BY source
                ORDER BY count DESC, source ASC
                """,
                params,
            ).fetchall()
        ]
        by_chat = [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT
                    COALESCE(chat_name, chat_id, display_phone_number, 'unknown') AS chat,
                    COALESCE(chat_id, '') AS chat_id,
                    COALESCE(is_group, 0) AS is_group,
                    COUNT(*) AS count
                FROM messages{where_sql}
                GROUP BY chat, chat_id, is_group
                ORDER BY count DESC, chat ASC
                LIMIT 30
                """,
                params,
            ).fetchall()
        ]
        by_sender = [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT
                    COALESCE(sender_name, sender_phone, 'unknown') AS sender,
                    COALESCE(sender_phone, sender_name, '') AS sender_value,
                    COUNT(*) AS count
                FROM messages{where_sql}
                GROUP BY sender, sender_value
                ORDER BY count DESC, sender ASC
                LIMIT 20
                """,
                params,
            ).fetchall()
        ]
        by_day = [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT date(COALESCE(timestamp, created_at)) AS day, COUNT(*) AS count
                FROM messages{where_sql}
                GROUP BY day
                ORDER BY day DESC
                LIMIT 30
                """,
                params,
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


def list_retention_rules():
    with get_connection() as conn:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM retention_rules
                ORDER BY enabled DESC, rule_type ASC, label ASC, value ASC
                """
            ).fetchall()
        ]


def upsert_retention_rule(rule_type, value, label=None, is_group=0):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO retention_rules (rule_type, value, label, is_group, enabled, created_at)
            VALUES (?, ?, ?, ?, 1, ?)
            ON CONFLICT(rule_type, value) DO UPDATE SET
                label = excluded.label,
                is_group = excluded.is_group,
                enabled = 1
            """,
            (rule_type, value, label or value, 1 if is_group else 0, now_iso()),
        )


def set_retention_rule_enabled(rule_id, enabled):
    with get_connection() as conn:
        conn.execute(
            "UPDATE retention_rules SET enabled = ? WHERE id = ?",
            (1 if enabled else 0, rule_id),
        )


def delete_retention_rule(rule_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM retention_rules WHERE id = ?", (rule_id,))


def should_store_message(record):
    with get_connection() as conn:
        rules = [
            dict(row)
            for row in conn.execute(
                "SELECT rule_type, value FROM retention_rules WHERE enabled = 1"
            ).fetchall()
        ]

    if not rules:
        return True

    chat_values = {
        record.get("chat_id"),
        record.get("group_id"),
        record.get("display_phone_number"),
    }
    sender_values = {
        record.get("sender_phone"),
        record.get("sender_name"),
    }

    for rule in rules:
        if rule["rule_type"] == "chat" and rule["value"] in chat_values:
            return True
        if rule["rule_type"] == "sender" and rule["value"] in sender_values:
            return True

    return False
