import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "messages.db"
BACKUP_DIR = ROOT / "artifacts" / "backups"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Safely clear live messages while preserving historical data."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--backup-first", action="store_true")
    parser.add_argument("--all-live", action="store_true")
    parser.add_argument("--confirm", action="store_true")
    return parser.parse_args(argv)


def table_count(connection, table):
    return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def historical_counts(connection):
    tables = [
        row[0]
        for row in connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name LIKE 'historical_%'
            ORDER BY name
            """
        ).fetchall()
    ]
    return {table: table_count(connection, table) for table in tables}


def create_backup(connection, database_path):
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = BACKUP_DIR / (
        f"{database_path.stem}-before-live-reset-{timestamp}-{uuid4().hex[:8]}.db"
    )
    with sqlite3.connect(backup_path) as backup:
        connection.backup(backup)
    return backup_path


def main(argv=None):
    args = parse_args(argv)
    database_path = args.db.resolve()
    if not database_path.exists():
        print(f"Database does not exist: {database_path}")
        return 1

    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    try:
        before = {
            "messages": table_count(connection, "messages"),
            "media_files": table_count(connection, "media_files"),
        }
        history_before = historical_counts(connection)
        print(f"Before: {before}")
        print(f"Historical baseline: {history_before}")

        if not args.all_live:
            print("No deletion selected. Add --all-live to target all live messages.")
            return 0
        if not args.confirm:
            print("No rows deleted. Add --confirm to authorize the reset.")
            return 0

        backup_path = None
        if args.backup_first:
            backup_path = create_backup(connection, database_path)
            print(f"Backup: {backup_path}")

        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "DELETE FROM media_files WHERE message_id IN (SELECT id FROM messages)"
        )
        connection.execute("DELETE FROM messages")

        after = {
            "messages": table_count(connection, "messages"),
            "media_files": table_count(connection, "media_files"),
        }
        history_after = historical_counts(connection)
        if history_before != history_after:
            raise RuntimeError("Historical baseline counts changed during reset")

        if args.dry_run:
            connection.rollback()
            print(f"Dry run after counts: {after}")
        else:
            connection.commit()
            print(f"After: {after}")
        print("Historical baseline preserved.")
        return 0
    except Exception as error:
        connection.rollback()
        print(f"Reset failed: {error}")
        return 1
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
