# Mor / McGuyver Historical Baseline

The historical baseline is a separate analytical layer built from prepared review
files. It is not live WhatsApp traffic and is never inserted into `messages`.

## Included Files

```text
seeds/mor_mcguyver_historical_seed_initial.json
seeds/review/mor_mcguyver_event_catalog.csv
seeds/review/mor_mcguyver_machine_summary.csv
seeds/review/mor_mcguyver_fault_family_summary.csv
```

The JSON seed is canonical. The CSV files are review aids.

Initial prepared coverage:

- 78 historical events.
- 24 machine summaries.
- 11 fault-family summaries.
- 25 events without a machine assignment.
- Period covered: 24 June 2026 through 6 July 2026.

Unassigned events remain unassigned. The importer does not infer missing machines.

## Import

From the repository root:

```bash
python scripts/import_historical_seed.py \
  seeds/mor_mcguyver_historical_seed_initial.json \
  --dry-run \
  --strict

python scripts/import_historical_seed.py \
  seeds/mor_mcguyver_historical_seed_initial.json \
  --backup-first \
  --strict
```

Use another database:

```bash
python scripts/import_historical_seed.py \
  seeds/mor_mcguyver_historical_seed_initial.json \
  --db /path/to/messages.db \
  --backup-first
```

The import is idempotent. A repeated import updates changed rows and skips rows
whose source-derived key and content are unchanged.

## Validation

```bash
python scripts/validate_historical_db.py
python -m unittest discover -s tests -v
python -m compileall -q app.py src scripts tests
```

The validator checks SQLite integrity, foreign keys, historical table presence,
and baseline record counts.

## Dashboard and APIs

The open `/dashboard` page contains a visually separate historical section with:

- Historical event and machine coverage KPIs.
- Machine ranking.
- Downtime and quality-risk indicators.
- Fault-family summary.
- Imported action plan when available.

Administration shows sources, reports, row counts, and import-run history.

Read-only APIs:

```text
GET /api/historical/summary
GET /api/historical/sources
GET /api/historical/machines
GET /api/historical/faults
GET /api/historical/actions
```

## Safe Live Reset

Preview only:

```bash
python scripts/reset_live_messages.py --all-live
```

Delete live messages after backup:

```bash
python scripts/reset_live_messages.py \
  --all-live \
  --backup-first \
  --confirm
```

The reset deletes linked `media_files` rows before `messages`. It preserves every
`historical_*` table, retention rules, machine rules, query audit, and webhook
events.
