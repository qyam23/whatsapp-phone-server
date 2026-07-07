import os
import sqlite3
import time
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.utils import now_iso


DB_PATH = Path(os.getenv("WHATSAPP_DB_PATH", str(Path("data") / "messages.db")))
ROOT_DIR = Path(__file__).resolve().parents[1]
HISTORICAL_MIGRATION = ROOT_DIR / "migrations" / "001_historical_baseline.sql"
HISTORICAL_TABLES = (
    "historical_sources",
    "historical_reports",
    "historical_kpis",
    "historical_machine_metrics",
    "historical_fault_families",
    "historical_action_plan",
    "historical_insights",
    "historical_events",
    "historical_monthly_load",
    "historical_fault_heatmap",
    "historical_import_runs",
)
PERIODS = {
    "12h": {"label": "Last 12 Hours", "duration": timedelta(hours=12), "buckets": 12},
    "7d": {"label": "Last 7 Days", "duration": timedelta(days=7), "buckets": 7},
    "30d": {"label": "Last 30 Days", "duration": timedelta(days=30), "buckets": 30},
}


@contextmanager
def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


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

            CREATE TABLE IF NOT EXISTS machine_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                machine_name TEXT NOT NULL,
                department TEXT,
                pattern TEXT NOT NULL,
                open_keywords TEXT DEFAULT 'open,opened,fault,down,stopped',
                close_keywords TEXT DEFAULT 'close,closed,fixed,resolved,running',
                enabled INTEGER DEFAULT 1,
                created_at TEXT,
                UNIQUE(machine_name, pattern)
            );

            CREATE TABLE IF NOT EXISTS query_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                question TEXT,
                tools_used TEXT,
                status TEXT NOT NULL,
                duration_ms INTEGER,
                created_at TEXT
            );
            """
        )
        _ensure_message_columns(conn)
        _ensure_historical_schema(conn)


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


def _ensure_historical_schema(conn):
    conn.executescript(HISTORICAL_MIGRATION.read_text(encoding="utf-8"))


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


def _active_scope_from_connection(connection):
    rules = [
        dict(row)
        for row in connection.execute(
            """
            SELECT id, rule_type, value, label, COALESCE(is_group, 0) AS is_group
            FROM retention_rules
            WHERE enabled = 1
            ORDER BY rule_type, label, value
            """
        ).fetchall()
    ]
    filtered = bool(rules)
    return {
        "filtered": filtered,
        "active_count": len(rules),
        "label": (
            "Live data filtered by monitored chats/groups/senders"
            if filtered
            else "Live data: all messages"
        ),
        "rules": rules,
    }


def get_active_retention_scope(connection=None):
    if connection is not None:
        return _active_scope_from_connection(connection)
    with get_connection() as connection:
        return _active_scope_from_connection(connection)


def _allows_name_fallback(rule):
    value = str(rule.get("value") or "").strip()
    label = str(rule.get("label") or "").strip()
    return not label or value.casefold() == label.casefold()


def message_matches_active_scope(record, scope=None):
    scope = scope or get_active_retention_scope()
    if not scope["filtered"]:
        return True

    is_group = bool(record.get("is_group"))
    for rule in scope["rules"]:
        if rule.get("is_group") and not is_group:
            continue

        value = str(rule.get("value") or "").strip()
        if rule["rule_type"] == "chat":
            stable_values = {
                str(item).strip()
                for item in (
                    record.get("chat_id"),
                    record.get("group_id"),
                    record.get("display_phone_number"),
                )
                if item
            }
            if value in stable_values:
                return True
            if _allows_name_fallback(rule) and value.casefold() == str(
                record.get("chat_name") or ""
            ).strip().casefold():
                return True

        if rule["rule_type"] == "sender":
            if value == str(record.get("sender_phone") or "").strip():
                return True
            if _allows_name_fallback(rule) and value.casefold() == str(
                record.get("sender_name") or ""
            ).strip().casefold():
                return True

    return False


def _scope_column(alias, column):
    return f"{alias}.{column}" if alias else column


def build_live_scope_where_clause(scope=None, table_alias=None):
    scope = scope or get_active_retention_scope()
    if not scope["filtered"]:
        return "", []

    rule_conditions = []
    params = []
    for rule in scope["rules"]:
        value = str(rule.get("value") or "").strip()
        matches = []
        match_params = []

        if rule["rule_type"] == "chat":
            for column in ("chat_id", "group_id", "display_phone_number"):
                matches.append(f"COALESCE({_scope_column(table_alias, column)}, '') = ?")
                match_params.append(value)
            if _allows_name_fallback(rule):
                matches.append(
                    f"COALESCE({_scope_column(table_alias, 'chat_name')}, '') = ? COLLATE NOCASE"
                )
                match_params.append(value)
        elif rule["rule_type"] == "sender":
            matches.append(
                f"COALESCE({_scope_column(table_alias, 'sender_phone')}, '') = ?"
            )
            match_params.append(value)
            if _allows_name_fallback(rule):
                matches.append(
                    f"COALESCE({_scope_column(table_alias, 'sender_name')}, '') = ? COLLATE NOCASE"
                )
                match_params.append(value)
        else:
            continue

        rule_sql = f"({' OR '.join(matches)})"
        if rule.get("is_group"):
            rule_sql = (
                f"(COALESCE({_scope_column(table_alias, 'is_group')}, 0) = 1 "
                f"AND {rule_sql})"
            )
        rule_conditions.append(rule_sql)
        params.extend(match_params)

    if not rule_conditions:
        return "0 = 1", []
    return f"({' OR '.join(rule_conditions)})", params


def _message_filters_where(filters=None, scope=None):
    filters = filters or {}
    conditions = []
    params = []

    scope_sql, scope_params = build_live_scope_where_clause(scope=scope)
    if scope_sql:
        conditions.append(scope_sql)
        params.extend(scope_params)
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
    with get_connection() as conn:
        scope = get_active_retention_scope(conn)
        where_sql, params = _message_filters_where(filters, scope=scope)
        query = f"SELECT * FROM messages{where_sql} ORDER BY COALESCE(timestamp, created_at) DESC, id DESC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
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
    with get_connection() as conn:
        scope = get_active_retention_scope(conn)
        where_sql, params = _message_filters_where(filters, scope=scope)
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
        "live_scope": {
            "filtered": scope["filtered"],
            "active_count": scope["active_count"],
            "label": scope["label"],
        },
    }


def _parse_timestamp(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _period_config(period):
    return period if period in PERIODS else "12h", PERIODS.get(period, PERIODS["12h"])


def _period_rows(conn, start, end, scope):
    scope_sql, scope_params = build_live_scope_where_clause(scope=scope)
    scope_filter = f" AND {scope_sql}" if scope_sql else ""
    return [
        dict(row)
        for row in conn.execute(
            f"""
            SELECT
                id,
                COALESCE(timestamp, created_at) AS occurred_at,
                chat_id,
                chat_name,
                COALESCE(is_group, 0) AS is_group,
                sender_phone,
                sender_name,
                message_type,
                text_body,
                media_caption
            FROM messages
            WHERE datetime(COALESCE(timestamp, created_at)) >= datetime(?)
              AND datetime(COALESCE(timestamp, created_at)) < datetime(?)
              {scope_filter}
            ORDER BY datetime(COALESCE(timestamp, created_at)) ASC, id ASC
            """,
            (start.isoformat(), end.isoformat(), *scope_params),
        ).fetchall()
    ]


def _identity(row, value_key, label_key):
    value = row.get(value_key) or row.get(label_key)
    label = row.get(label_key) or row.get(value_key) or "Unknown"
    return value, label


def _rank_rows(rows, value_key, label_key, limit=6, groups_only=False):
    counts = Counter()
    labels = {}
    for row in rows:
        if groups_only and not row.get("is_group"):
            continue
        value, label = _identity(row, value_key, label_key)
        if not value:
            continue
        counts[value] += 1
        labels[value] = label
    return [
        {"value": value, "label": labels[value], "count": count}
        for value, count in counts.most_common(limit)
    ]


def _comparison(current, previous):
    if previous == 0:
        return {"value": None, "label": "New" if current else "No change", "direction": "flat"}
    change = round(((current - previous) / previous) * 100)
    direction = "up" if change > 0 else "down" if change < 0 else "flat"
    return {"value": change, "label": f"{abs(change)}%", "direction": direction}


def _format_duration(seconds):
    if seconds is None:
        return "No data"
    if seconds < 60:
        return f"{round(seconds)} sec"
    if seconds < 3600:
        return f"{round(seconds / 60)} min"
    return f"{seconds / 3600:.1f} hr"


def _series(rows, start, duration, buckets):
    bucket_seconds = duration.total_seconds() / buckets
    counts = [0] * buckets
    for row in rows:
        occurred_at = _parse_timestamp(row.get("occurred_at"))
        if not occurred_at:
            continue
        index = int((occurred_at - start).total_seconds() // bucket_seconds)
        if 0 <= index < buckets:
            counts[index] += 1

    labels = []
    bucket_starts = []
    bucket_ends = []
    for index in range(buckets):
        point = start + timedelta(seconds=bucket_seconds * index)
        bucket_end = point + timedelta(seconds=bucket_seconds)
        bucket_starts.append(point.isoformat(timespec="seconds"))
        bucket_ends.append(bucket_end.isoformat(timespec="seconds"))
        labels.append(
            bucket_end.strftime("%H:%M")
            if duration <= timedelta(hours=12)
            else bucket_end.strftime("%d %b")
        )
    return labels, counts, bucket_starts, bucket_ends


def _keyword_list(value):
    return [item.strip().casefold() for item in (value or "").split(",") if item.strip()]


def _classify_machine_events(rows, rules):
    events = []
    for row in rows:
        text = " ".join(
            value for value in (row.get("text_body"), row.get("media_caption")) if value
        ).casefold()
        if not text:
            continue
        for rule in rules:
            if rule["pattern"].casefold() not in text:
                continue
            event_type = "mention"
            if any(keyword in text for keyword in _keyword_list(rule["close_keywords"])):
                event_type = "closed"
            elif any(keyword in text for keyword in _keyword_list(rule["open_keywords"])):
                event_type = "opened"
            events.append(
                {
                    "message_id": row["id"],
                    "machine": rule["machine_name"],
                    "department": rule["department"] or "Unassigned",
                    "event_type": event_type,
                    "occurred_at": row["occurred_at"],
                    "sender": row.get("sender_name") or row.get("sender_phone") or "Unknown",
                }
            )
    return events


def _machine_summary(events):
    opened = Counter()
    closed = Counter()
    active = {}
    resolution_seconds = []
    open_times = defaultdict(list)

    for event in events:
        occurred_at = _parse_timestamp(event["occurred_at"])
        if not occurred_at:
            continue
        machine = event["machine"]
        if event["event_type"] == "opened":
            opened[machine] += 1
            open_times[machine].append(occurred_at)
            active.setdefault(machine, event)
        elif event["event_type"] == "closed":
            closed[machine] += 1
            if machine in active:
                started = _parse_timestamp(active[machine]["occurred_at"])
                if started and occurred_at >= started:
                    resolution_seconds.append((occurred_at - started).total_seconds())
                active.pop(machine, None)

    recurrence = [
        {"machine": machine, "count": count}
        for machine, count in opened.most_common(8)
    ]
    open_intervals = []
    for times in open_times.values():
        open_intervals.extend(
            (current - previous).total_seconds()
            for previous, current in zip(times, times[1:])
        )

    return {
        "opened": sum(opened.values()),
        "closed": sum(closed.values()),
        "active": list(active.values()),
        "recurrence": recurrence,
        "average_resolution": _format_duration(
            sum(resolution_seconds) / len(resolution_seconds) if resolution_seconds else None
        ),
        "average_open_interval": _format_duration(
            sum(open_intervals) / len(open_intervals) if open_intervals else None
        ),
    }


def get_management_dashboard(period="12h", now=None):
    period, config = _period_config(period)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    start = now - config["duration"]
    previous_start = start - config["duration"]
    monthly_start = now - PERIODS["30d"]["duration"]

    with get_connection() as conn:
        scope = get_active_retention_scope(conn)
        current_rows = _period_rows(conn, start, now, scope)
        previous_rows = _period_rows(conn, previous_start, start, scope)
        monthly_rows = _period_rows(conn, monthly_start, now, scope)
        rules = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM machine_rules WHERE enabled = 1 ORDER BY machine_name, pattern"
            ).fetchall()
        ]
        scope_sql, scope_params = build_live_scope_where_clause(scope=scope)
        scope_where = f"WHERE {scope_sql}" if scope_sql else ""
        last_message = conn.execute(
            f"""
            SELECT COALESCE(timestamp, created_at) AS occurred_at
            FROM messages
            {scope_where}
            ORDER BY datetime(COALESCE(timestamp, created_at)) DESC, id DESC
            LIMIT 1
            """,
            scope_params,
        ).fetchone()

    sender_ranking = _rank_rows(current_rows, "sender_phone", "sender_name")
    group_ranking = _rank_rows(
        current_rows, "chat_id", "chat_name", groups_only=True
    )
    if not group_ranking:
        group_ranking = _rank_rows(current_rows, "chat_id", "chat_name")

    current_times = [
        parsed
        for parsed in (_parse_timestamp(row["occurred_at"]) for row in current_rows)
        if parsed
    ]
    gaps = [
        (current - previous).total_seconds()
        for previous, current in zip(current_times, current_times[1:])
        if current >= previous
    ]
    average_gap = sum(gaps) / len(gaps) if gaps else None
    labels, current_series, current_bucket_starts, current_bucket_ends = _series(
        current_rows, start, config["duration"], config["buckets"]
    )
    _, previous_series, previous_bucket_starts, previous_bucket_ends = _series(
        previous_rows, previous_start, config["duration"], config["buckets"]
    )

    current_machine_events = _classify_machine_events(current_rows, rules)
    monthly_machine_events = _classify_machine_events(monthly_rows, rules)
    current_machine_summary = _machine_summary(current_machine_events)
    monthly_machine_summary = _machine_summary(monthly_machine_events)

    active_senders = len(
        {
            row.get("sender_phone") or row.get("sender_name")
            for row in current_rows
            if row.get("sender_phone") or row.get("sender_name")
        }
    )
    previous_senders = len(
        {
            row.get("sender_phone") or row.get("sender_name")
            for row in previous_rows
            if row.get("sender_phone") or row.get("sender_name")
        }
    )
    active_groups = len(
        {
            row.get("chat_id") or row.get("chat_name")
            for row in current_rows
            if row.get("is_group") and (row.get("chat_id") or row.get("chat_name"))
        }
    )
    previous_groups = len(
        {
            row.get("chat_id") or row.get("chat_name")
            for row in previous_rows
            if row.get("is_group") and (row.get("chat_id") or row.get("chat_name"))
        }
    )
    period_hours = config["duration"].total_seconds() / 3600

    return {
        "period": period,
        "period_label": config["label"],
        "generated_at": now.isoformat(timespec="seconds"),
        "last_message_at": last_message["occurred_at"] if last_message else None,
        "metrics": {
            "messages": len(current_rows),
            "active_senders": active_senders,
            "active_groups": active_groups,
            "messages_per_hour": round(len(current_rows) / period_hours, 1),
            "average_gap": _format_duration(average_gap),
            "message_change": _comparison(len(current_rows), len(previous_rows)),
            "sender_change": _comparison(active_senders, previous_senders),
            "group_change": _comparison(active_groups, previous_groups),
        },
        "trend": {
            "labels": labels,
            "current": current_series,
            "previous": previous_series,
            "current_bucket_starts": current_bucket_starts,
            "current_bucket_ends": current_bucket_ends,
            "previous_bucket_starts": previous_bucket_starts,
            "previous_bucket_ends": previous_bucket_ends,
        },
        "top_senders": sender_ranking,
        "top_groups": group_ranking,
        "machine_data_available": bool(rules and monthly_machine_events),
        "machine_rules_count": len(rules),
        "machine_period": current_machine_summary,
        "machine_month": monthly_machine_summary,
        "live_scope": {
            "filtered": scope["filtered"],
            "active_count": scope["active_count"],
            "label": scope["label"],
        },
    }


@contextmanager
def get_readonly_connection(timeout_seconds=2):
    database_path = DB_PATH.resolve().as_posix()
    connection = sqlite3.connect(
        f"file:{database_path}?mode=ro",
        uri=True,
        timeout=1,
    )
    connection.row_factory = sqlite3.Row
    deadline = time.monotonic() + timeout_seconds
    connection.execute("PRAGMA query_only = ON")
    connection.set_progress_handler(
        lambda: 1 if time.monotonic() > deadline else 0,
        1000,
    )
    try:
        yield connection
    finally:
        connection.close()


def get_query_recent_messages(period="12h", chat=None, search=None, limit=20, now=None):
    period, config = _period_config(period)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    start = now.astimezone(timezone.utc) - config["duration"]
    conditions = [
        "datetime(COALESCE(timestamp, created_at)) >= datetime(?)",
        "datetime(COALESCE(timestamp, created_at)) < datetime(?)",
    ]
    params = [start.isoformat(), now.isoformat()]

    if chat:
        conditions.append(
            "(COALESCE(chat_name, '') LIKE ? OR COALESCE(chat_id, '') LIKE ?)"
        )
        params.extend([f"%{chat}%", f"%{chat}%"])
    if search:
        conditions.append(
            "(COALESCE(text_body, '') LIKE ? OR COALESCE(media_caption, '') LIKE ?)"
        )
        params.extend([f"%{search}%", f"%{search}%"])

    with get_readonly_connection() as connection:
        scope = get_active_retention_scope(connection)
        scope_sql, scope_params = build_live_scope_where_clause(scope=scope)
        if scope_sql:
            conditions.append(scope_sql)
            params.extend(scope_params)
        safe_limit = max(1, min(int(limit), 30))
        params.append(safe_limit)
        rows = connection.execute(
            f"""
            SELECT
                COALESCE(timestamp, created_at) AS occurred_at,
                COALESCE(chat_name, chat_id, 'Direct') AS chat,
                COALESCE(sender_name, 'Unknown') AS sender,
                COALESCE(message_type, 'unknown') AS message_type,
                COALESCE(text_body, media_caption, '') AS message
            FROM messages
            WHERE {" AND ".join(conditions)}
            ORDER BY datetime(COALESCE(timestamp, created_at)) DESC, id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return {"period": period, "messages": [dict(row) for row in rows]}


def record_query_audit(username, question, tools_used, status, duration_ms):
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO query_audit (
                username, question, tools_used, status, duration_ms, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                username,
                (question or "")[:1000],
                ",".join(tools_used or []),
                status,
                int(duration_ms),
                now_iso(),
            ),
        )


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


def list_machine_rules():
    with get_connection() as conn:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM machine_rules
                ORDER BY enabled DESC, department ASC, machine_name ASC, pattern ASC
                """
            ).fetchall()
        ]


def upsert_machine_rule(
    machine_name,
    pattern,
    department=None,
    open_keywords=None,
    close_keywords=None,
):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO machine_rules (
                machine_name, department, pattern, open_keywords, close_keywords, enabled, created_at
            )
            VALUES (?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(machine_name, pattern) DO UPDATE SET
                department = excluded.department,
                open_keywords = excluded.open_keywords,
                close_keywords = excluded.close_keywords,
                enabled = 1
            """,
            (
                machine_name,
                department or "",
                pattern,
                open_keywords or "open,opened,fault,down,stopped",
                close_keywords or "close,closed,fixed,resolved,running",
                now_iso(),
            ),
        )


def set_machine_rule_enabled(rule_id, enabled):
    with get_connection() as conn:
        conn.execute(
            "UPDATE machine_rules SET enabled = ? WHERE id = ?",
            (1 if enabled else 0, rule_id),
        )


def delete_machine_rule(rule_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM machine_rules WHERE id = ?", (rule_id,))


def should_store_message(record):
    with get_connection() as conn:
        scope = get_active_retention_scope(conn)
    return message_matches_active_scope(record, scope=scope)


def get_historical_machines(limit=50):
    safe_limit = max(1, min(int(limit), 200))
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                machine_key,
                machine,
                COALESCE(department, 'Unassigned') AS department,
                CAST(COALESCE(metric_value, 0) AS INTEGER) AS event_count,
                COALESCE(downtime_count, 0) AS downtime_count,
                COALESCE(quality_risk_count, 0) AS quality_risk_count,
                COALESCE(recurrence_score, 0) AS recurrence_score,
                COALESCE(severity, '0') AS severity,
                confidence_level,
                period_start,
                period_end
            FROM historical_machine_metrics
            ORDER BY event_count DESC, downtime_count DESC, machine ASC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_historical_faults(limit=50):
    safe_limit = max(1, min(int(limit), 200))
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                fault.fault_family,
                COALESCE(fault.occurrence_count, 0) AS occurrence_count,
                COALESCE(event_machines.machines_affected, 0) AS machines_affected,
                COALESCE(fault.downtime_count, 0) AS downtime_count,
                COALESCE(fault.quality_risk_count, 0) AS quality_risk_count,
                COALESCE(fault.recurrence_score, 0) AS recurrence_score,
                COALESCE(fault.severity, '0') AS severity,
                fault.confidence_level,
                fault.source_quote_or_summary
            FROM historical_fault_families AS fault
            LEFT JOIN (
                SELECT fault_family, COUNT(DISTINCT machine_key) AS machines_affected
                FROM historical_events
                WHERE machine_key IS NOT NULL AND machine_key != ''
                GROUP BY fault_family
            ) AS event_machines
                ON event_machines.fault_family = fault.fault_family
            ORDER BY occurrence_count DESC, fault.fault_family ASC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_historical_actions(limit=50):
    safe_limit = max(1, min(int(limit), 200))
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                record_key,
                COALESCE(priority, 'Unspecified') AS priority,
                machine,
                department,
                fault_family,
                action_text,
                owner_role,
                COALESCE(status, 'Open') AS status,
                target_date,
                confidence_level
            FROM historical_action_plan
            WHERE action_required = 1
            ORDER BY
                CASE LOWER(COALESCE(priority, ''))
                    WHEN 'critical' THEN 1
                    WHEN 'high' THEN 2
                    WHEN 'medium' THEN 3
                    WHEN 'low' THEN 4
                    ELSE 5
                END,
                target_date ASC,
                id ASC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_historical_sources(limit=50):
    safe_limit = max(1, min(int(limit), 200))
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                source.id,
                source.source_key,
                source.source_file,
                source.source_type,
                source.title,
                source.report_date,
                source.site,
                source.imported_at,
                source.updated_at,
                COUNT(report.id) AS report_count
            FROM historical_sources AS source
            LEFT JOIN historical_reports AS report ON report.source_id = source.id
            GROUP BY source.id
            ORDER BY source.updated_at DESC, source.id DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_historical_summary():
    machines = get_historical_machines()
    faults = get_historical_faults()
    actions = get_historical_actions()

    with get_connection() as conn:
        total_events = conn.execute(
            "SELECT COALESCE(SUM(event_count), 0) FROM historical_events"
        ).fetchone()[0]
        machines_covered = conn.execute(
            """
            SELECT COUNT(DISTINCT machine_key)
            FROM historical_machine_metrics
            WHERE machine_key IS NOT NULL AND machine_key != ''
            """
        ).fetchone()[0]
        coverage = conn.execute(
            """
            SELECT
                MIN(period_start) AS period_start,
                MAX(period_end) AS period_end,
                COUNT(*) AS report_count
            FROM historical_reports
            """
        ).fetchone()
        source_count = conn.execute(
            "SELECT COUNT(*) FROM historical_sources"
        ).fetchone()[0]

    top_recurring = machines[0] if machines else None
    top_downtime = (
        max(machines, key=lambda row: row["downtime_count"]) if machines else None
    )
    top_quality = (
        max(machines, key=lambda row: row["quality_risk_count"]) if machines else None
    )
    return {
        "available": bool(total_events or machines or faults),
        "label": "Historical managerial baseline, not raw live WhatsApp messages.",
        "metrics": {
            "total_events": total_events,
            "machines_covered": machines_covered,
            "top_recurring_machine": top_recurring,
            "top_downtime_machine": top_downtime,
            "top_quality_machine": top_quality,
        },
        "coverage": {
            "period_start": coverage["period_start"] if coverage else None,
            "period_end": coverage["period_end"] if coverage else None,
            "report_count": coverage["report_count"] if coverage else 0,
            "source_count": source_count,
        },
        "machines": machines,
        "faults": faults,
        "actions": actions,
    }


def get_historical_admin_data():
    with get_connection() as conn:
        counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in HISTORICAL_TABLES
        }
        reports = [
            dict(row)
            for row in conn.execute(
                """
                SELECT
                    report.report_key,
                    report.title,
                    report.report_type,
                    report.period_start,
                    report.period_end,
                    report.site,
                    report.confidence_level,
                    source.source_file
                FROM historical_reports AS report
                JOIN historical_sources AS source ON source.id = report.source_id
                ORDER BY report.updated_at DESC, report.id DESC
                LIMIT 50
                """
            ).fetchall()
        ]
        import_runs = [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM historical_import_runs
                ORDER BY started_at DESC, id DESC
                LIMIT 20
                """
            ).fetchall()
        ]
    return {
        "counts": counts,
        "sources": get_historical_sources(),
        "reports": reports,
        "import_runs": import_runs,
        "last_import": import_runs[0] if import_runs else None,
    }
