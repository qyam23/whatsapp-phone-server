import argparse
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "messages.db"
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
BASELINE_TABLES = (
    "historical_kpis",
    "historical_machine_metrics",
    "historical_fault_families",
    "historical_action_plan",
    "historical_insights",
    "historical_events",
    "historical_monthly_load",
    "historical_fault_heatmap",
)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Validate historical SQLite data.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    database_path = args.db.resolve()
    if not database_path.exists():
        print(f"Database does not exist: {database_path}")
        return 1

    connection = sqlite3.connect(
        f"file:{database_path.as_posix()}?mode=ro",
        uri=True,
    )
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_key_errors = connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()
        available_tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        missing_tables = [
            table for table in HISTORICAL_TABLES if table not in available_tables
        ]
        counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in HISTORICAL_TABLES
            if table in available_tables
        }
    finally:
        connection.close()

    print(f"Database: {database_path}")
    print(f"Integrity check: {integrity}")
    print(f"Foreign key errors: {len(foreign_key_errors)}")
    for table in HISTORICAL_TABLES:
        print(f"{table}: {counts.get(table, 'missing')}")

    baseline_count = sum(counts.get(table, 0) for table in BASELINE_TABLES)
    if integrity != "ok":
        print("FAILED: SQLite integrity check did not return ok.")
        return 1
    if foreign_key_errors:
        print("FAILED: foreign key violations were found.")
        return 1
    if missing_tables:
        print(f"FAILED: missing tables: {', '.join(missing_tables)}")
        return 1
    if not counts.get("historical_sources") or not counts.get("historical_reports"):
        print("FAILED: historical source/report metadata is missing.")
        return 1
    if baseline_count == 0:
        print("FAILED: no historical baseline records were found.")
        return 1

    print("Historical baseline validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
