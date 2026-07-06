# Historical Baseline Database and Dashboard Integration Map

## Scope

This report documents the current `whatsapp-phone-server` SQLite and dashboard
architecture and proposes a safe historical baseline layer for old project reports.
It is a design document only. No historical schema or application behavior has
been implemented yet.

## Current State

The application is a lightweight Flask service intended to run in Termux on a
Samsung phone. Baileys and Meta webhook events are normalized into SQLite.
Dashboard, administration, API, export, and optional AI features read from that
same database.

The default database is:

```text
data/messages.db
```

In the inspected checkout, `data/messages.db` had no message rows. The separate
desktop simulation database had 132 synthetic messages and 3 machine rules.

### Current SQLite Tables

#### `messages`

Purpose: the live WhatsApp event stream.

Columns:

```text
id INTEGER PRIMARY KEY AUTOINCREMENT
source TEXT DEFAULT 'meta'
chat_id TEXT
chat_name TEXT
is_group INTEGER DEFAULT 0
group_id TEXT
whatsapp_message_id TEXT UNIQUE
wa_business_phone_number_id TEXT
display_phone_number TEXT
sender_phone TEXT
sender_name TEXT
timestamp TEXT
message_type TEXT
text_body TEXT
media_id TEXT
media_mime_type TEXT
media_sha256 TEXT
media_filename TEXT
media_caption TEXT
media_path TEXT
raw_json_path TEXT
processing_status TEXT DEFAULT 'new'
created_at TEXT
```

Index: automatic unique index on `whatsapp_message_id`.

#### `webhook_events`

Purpose: lightweight receipt log for Meta and Baileys webhook activity.

```text
id INTEGER PRIMARY KEY AUTOINCREMENT
event_type TEXT
raw_json_path TEXT
received_at TEXT
```

No explicit indexes or foreign keys.

#### `media_files`

Purpose: future local/Drive media tracking.

```text
id INTEGER PRIMARY KEY AUTOINCREMENT
message_id INTEGER
media_id TEXT
local_path TEXT
drive_file_id TEXT
drive_link TEXT
mime_type TEXT
file_size INTEGER
sha256_hash TEXT
upload_status TEXT DEFAULT 'pending'
created_at TEXT
FOREIGN KEY(message_id) REFERENCES messages(id)
```

The foreign key is declared but current connections do not enable
`PRAGMA foreign_keys=ON`, so it is not enforced. No active code inserts rows into
this table. The Drive update helper is only a placeholder.

#### `retention_rules`

Purpose: select which chats/groups or senders are retained.

```text
id INTEGER PRIMARY KEY AUTOINCREMENT
rule_type TEXT NOT NULL
value TEXT NOT NULL
label TEXT
is_group INTEGER DEFAULT 0
enabled INTEGER DEFAULT 1
created_at TEXT
UNIQUE(rule_type, value)
```

Index: automatic unique index on `(rule_type, value)`.

#### `machine_rules`

Purpose: classify machine open, close, and mention events from message text.

```text
id INTEGER PRIMARY KEY AUTOINCREMENT
machine_name TEXT NOT NULL
department TEXT
pattern TEXT NOT NULL
open_keywords TEXT DEFAULT 'open,opened,fault,down,stopped'
close_keywords TEXT DEFAULT 'close,closed,fixed,resolved,running'
enabled INTEGER DEFAULT 1
created_at TEXT
UNIQUE(machine_name, pattern)
```

Index: automatic unique index on `(machine_name, pattern)`.

Machine classifications are calculated on every dashboard request. They are not
stored in a separate event/history table.

#### `query_audit`

Purpose: audit optional AI database questions.

```text
id INTEGER PRIMARY KEY AUTOINCREMENT
username TEXT NOT NULL
question TEXT
tools_used TEXT
status TEXT NOT NULL
duration_ms INTEGER
created_at TEXT
```

There are no persistent AI-result or AI-conversation tables.

### Tables That Do Not Exist

- No historical baseline tables.
- No transcript or transcription tables.
- No dashboard cache/materialized metric tables.
- No SQLite auth/user table.
- No persistent machine-event classification table.

Authentication uses a password hash in `src/auth.py` and Flask session cookies.

### Current Index Limitations

There are no explicit indexes for:

- Message timestamps.
- Creation timestamps.
- Source, chat, sender, or message type.
- `media_files.message_id`.
- Webhook receipt timestamps.
- AI audit timestamps.

The current dashboard therefore scans message rows for most calculations. This is
another reason not to mix large quantities of report-derived data into
`messages`.

## Current Write Paths

### Meta Webhook

`POST /webhook`:

1. Parses Meta payloads.
2. Reads enabled `retention_rules`.
3. If no record matches, writes an ignored event to `webhook_events`.
4. Otherwise saves raw JSON under `raw_events/`.
5. Inserts a receipt row into `webhook_events`.
6. Inserts normalized rows into `messages`.

Duplicate WhatsApp IDs are ignored by `INSERT OR IGNORE`.

### Baileys Companion

`POST /ingest/companion`:

1. Requires `source=baileys` and `message_id`.
2. Converts the payload into the shared message format.
3. Reads enabled `retention_rules`.
4. Saves raw JSON and a `webhook_events` row.
5. Inserts the normalized row into `messages`.

### Dashboard Administration

Administration routes write only to:

- `retention_rules`: add/upsert, enable/disable, delete.
- `machine_rules`: add/upsert, enable/disable, delete.

### Machine Classification

Machine classification does not write to SQLite. Dashboard code reads stored
messages, applies enabled text patterns, then computes open/close timing and
recurrence in Python.

### AI

Authenticated AI requests read bounded dashboard/message data. Every attempt
writes one row to `query_audit`. The model cannot execute arbitrary SQL.

### Media and Transcription

Media metadata is stored in `messages`. Media download, transcription, OCR, and
audio analysis are not implemented.

## Current Dashboard Read Paths

| Route | Data read |
|---|---|
| `/dashboard` | `messages`, enabled `machine_rules` |
| `/administration` | `messages`, `webhook_events`, `retention_rules`, `machine_rules` |
| `/messages` | filtered `messages` |
| `/api/stats` | `messages`, latest `webhook_events` |
| `/api/management` | `messages`, enabled `machine_rules` |
| `/api/messages` | filtered `messages` |
| `/export/messages.csv` | filtered `messages` |
| `/export/messages.json` | filtered `messages` |
| `/query`, `/api/ai/query` | bounded `messages` and calculated management data |

There is no historical or baseline view.

The 12-hour dashboard update is a browser reload. It is not a background job or
materialized aggregation. Management periods use the message event timestamp;
the Administration "today" count uses ingestion `created_at`.

## Recommended Historical Data Model

Use a hybrid model:

1. Keep `messages` exclusively for real WhatsApp events.
2. Store report-derived baseline facts in normalized `historical_*` tables.
3. Preserve source file, report, page, confidence, and summary provenance.
4. Build a combined management view only for compatible metrics.
5. Never create fake WhatsApp messages from historical reports.

This keeps live communication volume separate from historical production facts
and prevents report rows from corrupting sender, group, frequency, and timing
metrics.

## Recommended Historical Schema

All dates should use ISO-8601 text. Every database connection should enable
foreign keys. `machine_key` should be a stable normalized machine identifier that
can later be mapped to `machine_rules.machine_name`.

```sql
PRAGMA foreign_keys = ON;

CREATE TABLE historical_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_key TEXT NOT NULL UNIQUE,
    source_file TEXT NOT NULL,
    source_type TEXT NOT NULL,
    file_sha256 TEXT NOT NULL,
    title TEXT,
    report_date TEXT,
    site TEXT NOT NULL,
    metadata_json TEXT,
    imported_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(source_file, file_sha256)
);

CREATE TABLE historical_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL
        REFERENCES historical_sources(id) ON DELETE CASCADE,
    report_key TEXT NOT NULL,
    title TEXT NOT NULL,
    report_type TEXT,
    report_date TEXT,
    period_start TEXT,
    period_end TEXT,
    site TEXT NOT NULL,
    department TEXT,
    confidence_level TEXT,
    summary TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(source_id, report_key)
);

CREATE TABLE historical_kpis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL
        REFERENCES historical_reports(id) ON DELETE CASCADE,
    record_key TEXT NOT NULL,
    period_start TEXT,
    period_end TEXT,
    site TEXT,
    machine_key TEXT,
    machine TEXT,
    department TEXT,
    metric_type TEXT NOT NULL,
    metric_value REAL NOT NULL,
    metric_unit TEXT,
    target_value REAL,
    severity TEXT,
    confidence_level TEXT,
    source_page TEXT,
    source_quote_or_summary TEXT NOT NULL,
    notes TEXT,
    updated_at TEXT NOT NULL,
    UNIQUE(report_id, record_key)
);

CREATE TABLE historical_machine_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL
        REFERENCES historical_reports(id) ON DELETE CASCADE,
    record_key TEXT NOT NULL,
    period_start TEXT,
    period_end TEXT,
    site TEXT,
    machine_key TEXT NOT NULL,
    machine TEXT NOT NULL,
    department TEXT,
    metric_type TEXT NOT NULL,
    metric_value REAL,
    metric_unit TEXT,
    recurrence_score REAL,
    downtime_count INTEGER,
    quality_risk_count INTEGER,
    severity TEXT,
    confidence_level TEXT,
    source_page TEXT,
    source_quote_or_summary TEXT NOT NULL,
    notes TEXT,
    updated_at TEXT NOT NULL,
    UNIQUE(report_id, record_key)
);

CREATE TABLE historical_fault_families (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL
        REFERENCES historical_reports(id) ON DELETE CASCADE,
    record_key TEXT NOT NULL,
    period_start TEXT,
    period_end TEXT,
    site TEXT,
    machine_key TEXT,
    machine TEXT,
    department TEXT,
    fault_family TEXT NOT NULL,
    occurrence_count INTEGER,
    recurrence_score REAL,
    downtime_count INTEGER,
    quality_risk_count INTEGER,
    severity TEXT,
    confidence_level TEXT,
    source_page TEXT,
    source_quote_or_summary TEXT NOT NULL,
    notes TEXT,
    updated_at TEXT NOT NULL,
    UNIQUE(report_id, record_key)
);

CREATE TABLE historical_action_plan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL
        REFERENCES historical_reports(id) ON DELETE CASCADE,
    record_key TEXT NOT NULL,
    site TEXT,
    machine_key TEXT,
    machine TEXT,
    department TEXT,
    fault_family TEXT,
    action_required INTEGER NOT NULL DEFAULT 1,
    action_text TEXT NOT NULL,
    owner_role TEXT,
    priority TEXT,
    status TEXT,
    target_date TEXT,
    completed_at TEXT,
    confidence_level TEXT,
    source_page TEXT,
    source_quote_or_summary TEXT NOT NULL,
    notes TEXT,
    updated_at TEXT NOT NULL,
    UNIQUE(report_id, record_key)
);

CREATE TABLE historical_insights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL
        REFERENCES historical_reports(id) ON DELETE CASCADE,
    record_key TEXT NOT NULL,
    insight_type TEXT NOT NULL,
    site TEXT,
    machine_key TEXT,
    machine TEXT,
    department TEXT,
    fault_family TEXT,
    severity TEXT,
    confidence_level TEXT,
    source_page TEXT,
    source_quote_or_summary TEXT NOT NULL,
    notes TEXT,
    updated_at TEXT NOT NULL,
    UNIQUE(report_id, record_key)
);

CREATE TABLE historical_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL
        REFERENCES historical_reports(id) ON DELETE CASCADE,
    record_key TEXT NOT NULL,
    event_at TEXT,
    period_start TEXT,
    period_end TEXT,
    site TEXT,
    machine_key TEXT,
    machine TEXT,
    department TEXT,
    fault_family TEXT,
    event_type TEXT NOT NULL,
    event_count INTEGER DEFAULT 1,
    downtime_count INTEGER,
    quality_risk_count INTEGER,
    severity TEXT,
    confidence_level TEXT,
    source_page TEXT,
    source_quote_or_summary TEXT NOT NULL,
    notes TEXT,
    updated_at TEXT NOT NULL,
    UNIQUE(report_id, record_key)
);

CREATE TABLE historical_monthly_load (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL
        REFERENCES historical_reports(id) ON DELETE CASCADE,
    record_key TEXT NOT NULL,
    month_start TEXT NOT NULL,
    site TEXT,
    machine_key TEXT,
    machine TEXT,
    department TEXT,
    metric_type TEXT NOT NULL,
    load_value REAL,
    load_unit TEXT,
    capacity_value REAL,
    utilization_pct REAL,
    downtime_count INTEGER,
    confidence_level TEXT,
    source_page TEXT,
    source_quote_or_summary TEXT NOT NULL,
    notes TEXT,
    updated_at TEXT NOT NULL,
    UNIQUE(report_id, record_key)
);

CREATE TABLE historical_fault_heatmap (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL
        REFERENCES historical_reports(id) ON DELETE CASCADE,
    record_key TEXT NOT NULL,
    period_start TEXT,
    period_end TEXT,
    site TEXT,
    machine_key TEXT,
    machine TEXT,
    department TEXT,
    fault_family TEXT NOT NULL,
    occurrence_count INTEGER,
    recurrence_score REAL,
    downtime_count INTEGER,
    quality_risk_count INTEGER,
    severity TEXT,
    heat_score REAL,
    confidence_level TEXT,
    source_page TEXT,
    source_quote_or_summary TEXT NOT NULL,
    notes TEXT,
    updated_at TEXT NOT NULL,
    UNIQUE(report_id, record_key)
);

CREATE TABLE historical_import_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_key TEXT NOT NULL UNIQUE,
    seed_file TEXT NOT NULL,
    seed_sha256 TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    dry_run INTEGER NOT NULL DEFAULT 0,
    inserted_count INTEGER DEFAULT 0,
    updated_count INTEGER DEFAULT 0,
    skipped_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    backup_path TEXT,
    log_json TEXT
);

CREATE INDEX idx_historical_reports_period
    ON historical_reports(period_start, period_end);
CREATE INDEX idx_historical_kpis_metric
    ON historical_kpis(metric_type, period_start);
CREATE INDEX idx_historical_machine_period
    ON historical_machine_metrics(machine_key, period_start);
CREATE INDEX idx_historical_fault_family
    ON historical_fault_families(fault_family, machine_key);
CREATE INDEX idx_historical_actions_status
    ON historical_action_plan(status, priority);
CREATE INDEX idx_historical_events_time
    ON historical_events(event_at, machine_key);
CREATE INDEX idx_historical_monthly_machine
    ON historical_monthly_load(month_start, machine_key);
CREATE INDEX idx_historical_heatmap
    ON historical_fault_heatmap(department, machine_key, fault_family);
```

### Table-to-Screen Mapping

| Table | Purpose | Dashboard consumer |
|---|---|---|
| `historical_sources` | File identity, hash, provenance | Administration |
| `historical_reports` | Logical report and coverage period | Administration and Historical overview |
| `historical_kpis` | Baseline KPI values and targets | Historical KPI cards |
| `historical_machine_metrics` | Machine-level baseline measures | Machine comparison |
| `historical_fault_families` | Fault Pareto and recurrence | Fault analysis |
| `historical_action_plan` | Historical and open actions | Administration and management follow-up |
| `historical_insights` | Evidence-backed report conclusions | Historical management summary |
| `historical_events` | Dated baseline events | Historical timeline |
| `historical_monthly_load` | Monthly machine load/capacity | Rolling monthly chart |
| `historical_fault_heatmap` | Machine/fault severity matrix | Heatmap |
| `historical_import_runs` | Import audit and backup reference | Administration |

## Historical Import File Format

Use JSON as the canonical seed format. CSV can be used as a human-editable staging
format, but it should be converted and validated into the canonical JSON before
database import.

Root structure:

```json
{
  "schema_version": 1,
  "dataset_id": "mor-historical-baseline",
  "generated_at": "<ISO-8601 timestamp>",
  "items": []
}
```

Every item must contain every key below. Values that do not apply to a particular
record type may be `null`.

```json
{
  "record_key": "<stable source-derived key>",
  "record_type": "kpi|machine_metric|fault_family|action_plan|insight|event|monthly_load|fault_heatmap",
  "report_key": "<stable report key>",
  "report_title": "<report title>",
  "source_file": "<original filename>",
  "source_type": "pdf|docx|xlsx|csv|json|image|manual",
  "report_date": "YYYY-MM-DD",
  "period_start": "<ISO date or null>",
  "period_end": "<ISO date or null>",
  "site": "Mor Factory, Sderot, Israel",
  "machine_key": null,
  "machine": null,
  "department": null,
  "fault_family": null,
  "metric_type": null,
  "metric_value": null,
  "metric_unit": null,
  "severity": null,
  "recurrence_score": null,
  "downtime_count": null,
  "quality_risk_count": null,
  "action_required": false,
  "owner_role": null,
  "confidence_level": "high|medium|low",
  "source_page": null,
  "source_quote_or_summary": "<short evidence summary>",
  "notes": null
}
```

Additional type-specific fields may include:

- `target_value`
- `occurrence_count`
- `action_text`
- `priority`
- `status`
- `target_date`
- `completed_at`
- `insight_type`
- `event_at`
- `event_type`
- `event_count`
- `month_start`
- `load_value`
- `load_unit`
- `capacity_value`
- `utilization_pct`
- `heat_score`

Use concise evidence summaries instead of copying long passages from reports.

## Recommended GitHub Structure

```text
migrations/
  001_historical_baseline.sql

seeds/
  mor_historical_seed.json
  schema/
    mor_historical_seed.schema.json
  templates/
    historical_kpis.csv
    historical_machine_metrics.csv
    historical_fault_families.csv
    historical_action_plan.csv

scripts/
  import_historical_seed.py
  reset_live_messages.py
  validate_historical_db.py

docs/
  HISTORICAL_BASELINE_INTEGRATION_MAP.md
  HISTORICAL_FIELD_DICTIONARY.md

artifacts/
  historical-source-files/
  import-logs/
  backups/
```

Commit schemas, templates, scripts, and documentation. Real reports or extracted
seed content should only be committed after confirming that the GitHub repository
has suitable privacy and access controls.

## Import Script Design

Target command:

```bash
python scripts/import_historical_seed.py seeds/mor_historical_seed.json
```

Recommended options:

```text
--db PATH
--dry-run
--backup-first
--strict
--log-file PATH
```

Required behavior:

1. Resolve `WHATSAPP_DB_PATH`, or use `data/messages.db`.
2. Parse and validate the JSON schema version.
3. Validate required keys, record types, enums, dates, date ranges, finite numeric
   values, and duplicate record keys.
4. Calculate the seed and source file hashes.
5. For `--dry-run`, execute migrations and upserts inside a transaction that is
   rolled back.
6. For `--backup-first`, use Python's SQLite backup API before any migration.
7. Enable foreign keys and a reasonable busy timeout.
8. Apply migrations without destructive schema changes.
9. Upsert sources, reports, and child rows by their stable unique keys.
10. Perform the real import in one transaction.
11. Never update or delete `messages`, `webhook_events`, `media_files`,
    `retention_rules`, `machine_rules`, or `query_audit`.
12. Record inserted, updated, skipped, and failed counts.
13. Write results to stdout, `historical_import_runs`, and an artifact log.

The script should use Python standard-library `json`, `hashlib`, `sqlite3`,
`argparse`, and `pathlib` to remain Termux-compatible.

## Reset Strategy

Target command:

```bash
python scripts/reset_live_messages.py --backup-first
```

The safe default should remove only recognized test/demo messages:

```text
source IN ('desktop-demo', 'test')
OR processing_status = 'demo'
OR whatsapp_message_id LIKE 'desktop-demo-%'
```

Recommended options:

```text
--db PATH
--dry-run
--backup-first
--message-id ID
--all-live
--include-webhook-events
--confirm
```

Deletion order:

1. Preview selected message IDs and counts.
2. Create a SQLite backup.
3. Delete `media_files` rows linked to selected messages.
4. Delete only the selected `messages`.
5. Optionally clear matching webhook receipt rows when explicitly requested.
6. Commit in one transaction.

Always preserve:

- Every `historical_*` table.
- `retention_rules`.
- `machine_rules`.
- `query_audit`.
- Authentication behavior and Flask configuration.

Raw JSON files should not be removed automatically. They need a separate,
explicit retention workflow.

## Dashboard Integration Plan

### Dashboard

Add three clear views:

1. **Live WhatsApp**: current 12-hour, 7-day, and 30-day message activity.
2. **Historical Baseline**: report coverage, baseline KPIs, machine trends, fault
   families, heatmap, events, and action plans.
3. **Combined Management**: compatible live machine metrics compared with
   historical machine baselines.

Do not add report counts to message counts. Combined views should compare
compatible metric types, units, machines, and time grains.

### Administration

Add:

- Historical source catalog.
- Report list and coverage periods.
- Import run status and validation errors.
- Record counts by historical table.
- Source hash and last-import information.
- Coverage warnings for missing machines, periods, or confidence levels.

Initial imports should remain command-line operations. Browser file upload can be
considered later after authentication and upload-size protections are designed.

### API Routes

Add separate routes without changing existing API contracts:

```text
GET /api/historical/summary
GET /api/historical/sources
GET /api/historical/machines
GET /api/historical/faults
GET /api/historical/actions
GET /api/management/combined
```

Recommended filters:

```text
site
department
machine
fault_family
period_start
period_end
severity
confidence_level
```

Historical AI tools may be added later as authenticated, allowlisted server-side
functions. The model should never receive a database connection or arbitrary SQL.

## Implementation Plan

1. Add migration support and the historical schema.
2. Add seed schema, field dictionary, and CSV templates.
3. Implement dry-run, backup, validation, and idempotent import.
4. Implement the safe live-test reset utility.
5. Add historical database query functions and unit tests.
6. Add historical API routes while preserving current responses.
7. Add separate dashboard and Administration views.
8. Add combined comparisons only after machine and metric mappings reconcile.
9. Validate on desktop, then deploy through Git and run the import on Termux.

## Validation Commands

### Schema and Import

```bash
python scripts/import_historical_seed.py seeds/mor_historical_seed.json --dry-run
python scripts/import_historical_seed.py seeds/mor_historical_seed.json --backup-first
python scripts/validate_historical_db.py

sqlite3 data/messages.db "PRAGMA integrity_check;"
sqlite3 data/messages.db "PRAGMA foreign_key_check;"
sqlite3 data/messages.db "SELECT COUNT(*) FROM historical_sources;"
sqlite3 data/messages.db "SELECT COUNT(*) FROM historical_reports;"
sqlite3 data/messages.db "SELECT COUNT(*) FROM historical_kpis;"
```

### Application

```bash
python -m unittest discover -s tests -v
python -m compileall -q app.py src scripts tests

curl -f http://127.0.0.1:8000/health
curl -f http://127.0.0.1:8000/dashboard
curl -f http://127.0.0.1:8000/administration
curl -f http://127.0.0.1:8000/api/historical/summary
```

### Baileys and Retention

Ingest one uniquely identified validation message using a chat or sender allowed
by the currently enabled retention rules. Confirm it appears in `messages`, then
remove only that ID:

```bash
python scripts/reset_live_messages.py \
  --backup-first \
  --message-id validation-historical-baseline-001
```

Afterward confirm:

- Historical row counts did not change.
- `retention_rules` did not change.
- `machine_rules` did not change.
- No old test messages remain.
- A new real Baileys event can still be ingested.
- Dashboard and Administration still open.

## Key Decision

Historical baseline data should be stored as evidence-backed report facts, not as
synthetic WhatsApp traffic. This preserves the meaning of the live dashboard while
allowing a trustworthy baseline and combined management layer to be built on the
same SQLite database.
