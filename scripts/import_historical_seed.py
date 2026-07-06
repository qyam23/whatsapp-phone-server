import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "messages.db"
MIGRATION = ROOT / "migrations" / "001_historical_baseline.sql"
BACKUP_DIR = ROOT / "artifacts" / "backups"
ALLOWED_RECORD_TYPES = {
    "kpi",
    "machine_metric",
    "fault_family",
    "action_plan",
    "insight",
    "event",
    "monthly_load",
    "fault_heatmap",
}
REQUIRED_FIELDS = {
    "record_key",
    "record_type",
    "report_key",
    "source_file",
    "source_type",
    "site",
    "confidence_level",
    "source_quote_or_summary",
}
LIVE_TABLES = (
    "messages",
    "webhook_events",
    "media_files",
    "retention_rules",
    "machine_rules",
    "query_audit",
)
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


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def connect_database(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def apply_migration(connection):
    connection.executescript(MIGRATION.read_text(encoding="utf-8"))


def create_backup(connection, database_path):
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = (
        BACKUP_DIR / f"{database_path.stem}-{timestamp}-{uuid4().hex[:8]}.db"
    )
    with sqlite3.connect(backup_path) as backup:
        connection.backup(backup)
    return backup_path


def table_counts(connection, tables):
    counts = {}
    for table in tables:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        counts[table] = (
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if exists
            else 0
        )
    return counts


def validate_seed(seed, strict=False):
    errors = []
    warnings = []
    if not seed.get("schema_version"):
        errors.append("schema_version is required")
    if not seed.get("dataset_id"):
        errors.append("dataset_id is required")
    items = seed.get("items")
    if not isinstance(items, list):
        return ["items must be a list"], warnings

    seen_keys = set()
    for index, item in enumerate(items):
        label = f"items[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        missing = [
            field
            for field in REQUIRED_FIELDS
            if field not in item or item[field] is None or str(item[field]).strip() == ""
        ]
        if missing:
            errors.append(f"{label} missing required fields: {', '.join(sorted(missing))}")
        record_type = item.get("record_type")
        if record_type not in ALLOWED_RECORD_TYPES:
            errors.append(f"{label} has unsupported record_type: {record_type}")
        record_key = item.get("record_key")
        if record_key in seen_keys:
            errors.append(f"{label} duplicates record_key: {record_key}")
        seen_keys.add(record_key)

        if record_type == "machine_metric" and (
            not item.get("machine_key") or not item.get("machine")
        ):
            errors.append(f"{label} machine_metric requires machine_key and machine")
        if record_type in {"fault_family", "fault_heatmap"} and not item.get(
            "fault_family"
        ):
            errors.append(f"{label} requires fault_family")
        if record_type == "event" and not item.get("event_type"):
            errors.append(f"{label} event requires event_type")
        if record_type == "action_plan" and not item.get("action_text"):
            errors.append(f"{label} action_plan requires action_text")
        if record_type == "insight" and not item.get("insight_type"):
            errors.append(f"{label} insight requires insight_type")
        if record_type == "monthly_load" and not item.get("month_start"):
            errors.append(f"{label} monthly_load requires month_start")
        if strict and item.get("confidence_level") not in {"high", "medium", "low"}:
            errors.append(f"{label} has invalid confidence_level")

    unassigned_events = sum(
        1
        for item in items
        if item.get("record_type") == "event" and not item.get("machine_key")
    )
    if unassigned_events:
        warnings.append(
            f"{unassigned_events} historical events have no machine assignment"
        )
    return errors, warnings


def normalize_value(value):
    if isinstance(value, bool):
        return 1 if value else 0
    return value


def upsert_record(connection, table, unique_values, values, counters):
    where = " AND ".join(f"{column} = ?" for column in unique_values)
    unique_params = tuple(unique_values.values())
    existing = connection.execute(
        f"SELECT * FROM {table} WHERE {where}",
        unique_params,
    ).fetchone()
    normalized = {key: normalize_value(value) for key, value in values.items()}
    comparison_values = {
        key: value
        for key, value in normalized.items()
        if key not in {"created_at", "imported_at", "updated_at"}
    }

    if existing is None:
        columns = {**unique_values, **normalized}
        placeholders = ", ".join("?" for _ in columns)
        connection.execute(
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
            tuple(columns.values()),
        )
        counters["inserted"] += 1
    elif all(existing[key] == value for key, value in comparison_values.items()):
        counters["skipped"] += 1
    else:
        update_values = {
            key: value
            for key, value in normalized.items()
            if key not in {"created_at", "imported_at"}
        }
        assignments = ", ".join(f"{column} = ?" for column in update_values)
        connection.execute(
            f"UPDATE {table} SET {assignments} WHERE {where}",
            tuple(update_values.values()) + unique_params,
        )
        counters["updated"] += 1

    return connection.execute(
        f"SELECT id FROM {table} WHERE {where}",
        unique_params,
    ).fetchone()["id"]


def child_record(item, timestamp):
    common = {
        "period_start": item.get("period_start"),
        "period_end": item.get("period_end"),
        "site": item.get("site"),
        "machine_key": item.get("machine_key"),
        "machine": item.get("machine"),
        "department": item.get("department"),
        "confidence_level": item.get("confidence_level"),
        "source_page": item.get("source_page"),
        "source_quote_or_summary": item.get("source_quote_or_summary"),
        "notes": item.get("notes"),
        "updated_at": timestamp,
    }
    record_type = item["record_type"]
    if record_type == "kpi":
        return "historical_kpis", {
            **common,
            "metric_type": item.get("metric_type"),
            "metric_value": item.get("metric_value"),
            "metric_unit": item.get("metric_unit"),
            "target_value": item.get("target_value"),
            "severity": item.get("severity"),
        }
    if record_type == "machine_metric":
        return "historical_machine_metrics", {
            **common,
            "metric_type": item.get("metric_type"),
            "metric_value": item.get("metric_value"),
            "metric_unit": item.get("metric_unit"),
            "recurrence_score": item.get("recurrence_score"),
            "downtime_count": item.get("downtime_count"),
            "quality_risk_count": item.get("quality_risk_count"),
            "severity": item.get("severity"),
        }
    if record_type == "fault_family":
        return "historical_fault_families", {
            **common,
            "fault_family": item.get("fault_family"),
            "occurrence_count": item.get("occurrence_count", item.get("metric_value")),
            "recurrence_score": item.get("recurrence_score"),
            "downtime_count": item.get("downtime_count"),
            "quality_risk_count": item.get("quality_risk_count"),
            "severity": item.get("severity"),
        }
    if record_type == "action_plan":
        action = {
            key: value
            for key, value in common.items()
            if key not in {"period_start", "period_end"}
        }
        return "historical_action_plan", {
            **action,
            "fault_family": item.get("fault_family"),
            "action_required": item.get("action_required", True),
            "action_text": item.get("action_text"),
            "owner_role": item.get("owner_role"),
            "priority": item.get("priority"),
            "status": item.get("status"),
            "target_date": item.get("target_date"),
            "completed_at": item.get("completed_at"),
        }
    if record_type == "insight":
        insight = {
            key: value
            for key, value in common.items()
            if key not in {"period_start", "period_end"}
        }
        return "historical_insights", {
            **insight,
            "insight_type": item.get("insight_type"),
            "fault_family": item.get("fault_family"),
            "severity": item.get("severity"),
        }
    if record_type == "event":
        return "historical_events", {
            **common,
            "event_at": item.get("event_at"),
            "fault_family": item.get("fault_family"),
            "event_type": item.get("event_type"),
            "event_count": item.get("event_count", 1),
            "downtime_count": item.get("downtime_count"),
            "quality_risk_count": item.get("quality_risk_count"),
            "severity": item.get("severity"),
        }
    if record_type == "monthly_load":
        monthly = {
            key: value
            for key, value in common.items()
            if key not in {"period_start", "period_end"}
        }
        return "historical_monthly_load", {
            **monthly,
            "month_start": item.get("month_start"),
            "metric_type": item.get("metric_type"),
            "load_value": item.get("load_value", item.get("metric_value")),
            "load_unit": item.get("load_unit", item.get("metric_unit")),
            "capacity_value": item.get("capacity_value"),
            "utilization_pct": item.get("utilization_pct"),
            "downtime_count": item.get("downtime_count"),
        }
    return "historical_fault_heatmap", {
        **common,
        "fault_family": item.get("fault_family"),
        "occurrence_count": item.get("occurrence_count", item.get("metric_value")),
        "recurrence_score": item.get("recurrence_score"),
        "downtime_count": item.get("downtime_count"),
        "quality_risk_count": item.get("quality_risk_count"),
        "severity": item.get("severity"),
        "heat_score": item.get("heat_score"),
    }


def import_items(connection, seed, seed_hash):
    timestamp = now_iso()
    counters = {"inserted": 0, "updated": 0, "skipped": 0, "errors": 0}
    source_ids = {}
    report_ids = {}

    for item in seed["items"]:
        source_key = f"{seed['dataset_id']}:{item['source_file']}"
        if source_key not in source_ids:
            source_ids[source_key] = upsert_record(
                connection,
                "historical_sources",
                {"source_key": source_key},
                {
                    "source_file": item["source_file"],
                    "source_type": item["source_type"],
                    "file_sha256": item.get("file_sha256"),
                    "title": item["source_file"],
                    "report_date": item.get("report_date"),
                    "site": item["site"],
                    "metadata_json": json.dumps(
                        {
                            "dataset_id": seed["dataset_id"],
                            "seed_sha256": seed_hash,
                            "source_summary": seed.get("source_summary"),
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    "imported_at": timestamp,
                    "updated_at": timestamp,
                },
                counters,
            )

        report_cache_key = (source_ids[source_key], item["report_key"])
        if report_cache_key not in report_ids:
            report_ids[report_cache_key] = upsert_record(
                connection,
                "historical_reports",
                {
                    "source_id": source_ids[source_key],
                    "report_key": item["report_key"],
                },
                {
                    "title": item.get("report_title") or item["report_key"],
                    "report_type": item.get("report_type") or "historical_baseline",
                    "report_date": item.get("report_date"),
                    "period_start": item.get("period_start"),
                    "period_end": item.get("period_end"),
                    "site": item["site"],
                    "department": item.get("report_department"),
                    "confidence_level": item.get("report_confidence_level") or "mixed",
                    "summary": item.get("report_summary")
                    or "Historical baseline imported from the prepared seed.",
                    "notes": item.get("report_notes"),
                    "created_at": timestamp,
                    "updated_at": timestamp,
                },
                counters,
            )

        table, values = child_record(item, timestamp)
        upsert_record(
            connection,
            table,
            {
                "report_id": report_ids[report_cache_key],
                "record_key": item["record_key"],
            },
            values,
            counters,
        )

    return counters


def write_import_run(
    connection,
    seed_path,
    seed_hash,
    started_at,
    status,
    dry_run,
    counters,
    backup_path,
    log,
):
    connection.execute(
        """
        INSERT INTO historical_import_runs (
            run_key, seed_file, seed_sha256, started_at, finished_at, status,
            dry_run, inserted_count, updated_count, skipped_count, error_count,
            backup_path, log_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            uuid4().hex,
            str(seed_path),
            seed_hash,
            started_at,
            now_iso(),
            status,
            1 if dry_run else 0,
            counters["inserted"],
            counters["updated"],
            counters["skipped"],
            counters["errors"],
            str(backup_path) if backup_path else None,
            json.dumps(log, ensure_ascii=False, sort_keys=True),
        ),
    )


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Import historical baseline JSON.")
    parser.add_argument("seed", type=Path)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--backup-first", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--log-file", type=Path)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    seed_path = args.seed.resolve()
    database_path = args.db.resolve()
    started_at = now_iso()

    try:
        seed = json.loads(seed_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"Seed read failed: {error}", file=sys.stderr)
        return 2

    errors, warnings = validate_seed(seed, strict=args.strict)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2

    seed_hash = file_sha256(seed_path)
    connection = connect_database(database_path)
    backup_path = None
    try:
        live_before = table_counts(connection, LIVE_TABLES)
        if args.backup_first:
            backup_path = create_backup(connection, database_path)
        apply_migration(connection)

        connection.execute("BEGIN IMMEDIATE")
        counters = import_items(connection, seed, seed_hash)
        historical_counts = table_counts(connection, HISTORICAL_TABLES[:-1])
        live_after = table_counts(connection, LIVE_TABLES)
        if live_before != live_after:
            raise RuntimeError("Live table counts changed during historical import")

        log = {
            "dataset_id": seed["dataset_id"],
            "warnings": warnings,
            "live_counts_before": live_before,
            "live_counts_after": live_after,
            "historical_counts": historical_counts,
        }
        if args.dry_run:
            connection.rollback()
            write_import_run(
                connection,
                seed_path,
                seed_hash,
                started_at,
                "dry_run",
                True,
                counters,
                backup_path,
                log,
            )
            connection.commit()
        else:
            write_import_run(
                connection,
                seed_path,
                seed_hash,
                started_at,
                "completed",
                False,
                counters,
                backup_path,
                log,
            )
            connection.commit()

        summary = {
            "status": "dry_run" if args.dry_run else "completed",
            "database": str(database_path),
            "seed": str(seed_path),
            "backup": str(backup_path) if backup_path else None,
            **counters,
            "warnings": warnings,
            "record_counts": historical_counts,
            "live_tables_unchanged": live_before == live_after,
        }
        rendered = json.dumps(summary, ensure_ascii=False, indent=2)
        print(rendered)
        if args.log_file:
            args.log_file.parent.mkdir(parents=True, exist_ok=True)
            args.log_file.write_text(rendered + "\n", encoding="utf-8")
        return 0
    except Exception as error:
        connection.rollback()
        print(f"Import failed: {error}", file=sys.stderr)
        return 1
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
