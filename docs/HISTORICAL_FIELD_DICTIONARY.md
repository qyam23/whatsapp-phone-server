# Historical Baseline Field Dictionary

## Seed Envelope

| Field | Meaning |
|---|---|
| `schema_version` | Import contract version |
| `dataset_id` | Stable identifier for the prepared dataset |
| `generated_at` | Seed generation timestamp |
| `source_summary` | Prepared source coverage metadata |
| `items` | Historical records routed by `record_type` |

## Required Item Fields

| Field | Meaning |
|---|---|
| `record_key` | Stable idempotent key within a report |
| `record_type` | Destination historical table selector |
| `report_key` | Stable logical report identifier |
| `report_title` | Human-readable report name |
| `source_file` | Prepared source filename |
| `source_type` | Source format, such as `csv` |
| `report_date` | Report preparation date |
| `period_start`, `period_end` | Historical coverage interval |
| `site` | Factory/site name |
| `confidence_level` | `high`, `medium`, or `low` |
| `source_quote_or_summary` | Short evidence excerpt or prepared summary |

## Shared Analytical Fields

| Field | Meaning |
|---|---|
| `machine_key` | Stable normalized machine identifier |
| `machine` | Display name |
| `department` | Production department |
| `fault_family` | Prepared fault grouping |
| `severity` | Prepared severity value; initial seed uses `0` through `4` |
| `recurrence_score` | Prepared recurrence/average-severity indicator |
| `downtime_count` | Count of records flagged for downtime |
| `quality_risk_count` | Count of records flagged for quality risk |
| `action_required` | Whether follow-up was indicated in the prepared source |
| `owner_role` | Suggested responsible role when supplied |
| `source_page` | Source row/page reference |
| `notes` | Qualification or interpretation note |

## Record Types

| `record_type` | Destination | Required type-specific fields |
|---|---|---|
| `kpi` | `historical_kpis` | `metric_type`, `metric_value` |
| `machine_metric` | `historical_machine_metrics` | `machine_key`, `machine`, `metric_type` |
| `fault_family` | `historical_fault_families` | `fault_family` |
| `action_plan` | `historical_action_plan` | `action_text` |
| `insight` | `historical_insights` | `insight_type` |
| `event` | `historical_events` | `event_type`, normally `event_at` |
| `monthly_load` | `historical_monthly_load` | `month_start`, `metric_type` |
| `fault_heatmap` | `historical_fault_heatmap` | `fault_family` |

## Initial Seed Interpretation

- Machine `metric_value` is imported as the historical event count.
- Fault-family `metric_value` is imported as `occurrence_count`.
- Event `event_count` defaults to `1`.
- Historical rows are evidence summaries, not verified production downtime.
- Missing machines remain null and are excluded from machine coverage counts.
- The prepared seed has no action-plan, KPI, insight, monthly-load, or heatmap
  records yet; those tables intentionally remain empty.
