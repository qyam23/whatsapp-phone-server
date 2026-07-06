CREATE TABLE IF NOT EXISTS historical_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_key TEXT NOT NULL UNIQUE,
    source_file TEXT NOT NULL,
    source_type TEXT NOT NULL,
    file_sha256 TEXT,
    title TEXT,
    report_date TEXT,
    site TEXT,
    metadata_json TEXT,
    imported_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS historical_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER REFERENCES historical_sources(id) ON DELETE CASCADE,
    report_key TEXT NOT NULL,
    title TEXT NOT NULL,
    report_type TEXT,
    report_date TEXT,
    period_start TEXT,
    period_end TEXT,
    site TEXT,
    department TEXT,
    confidence_level TEXT,
    summary TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(source_id, report_key)
);

CREATE TABLE IF NOT EXISTS historical_kpis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER REFERENCES historical_reports(id) ON DELETE CASCADE,
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
    source_quote_or_summary TEXT,
    notes TEXT,
    updated_at TEXT NOT NULL,
    UNIQUE(report_id, record_key)
);

CREATE TABLE IF NOT EXISTS historical_machine_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER REFERENCES historical_reports(id) ON DELETE CASCADE,
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
    source_quote_or_summary TEXT,
    notes TEXT,
    updated_at TEXT NOT NULL,
    UNIQUE(report_id, record_key)
);

CREATE TABLE IF NOT EXISTS historical_fault_families (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER REFERENCES historical_reports(id) ON DELETE CASCADE,
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
    source_quote_or_summary TEXT,
    notes TEXT,
    updated_at TEXT NOT NULL,
    UNIQUE(report_id, record_key)
);

CREATE TABLE IF NOT EXISTS historical_action_plan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER REFERENCES historical_reports(id) ON DELETE CASCADE,
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
    source_quote_or_summary TEXT,
    notes TEXT,
    updated_at TEXT NOT NULL,
    UNIQUE(report_id, record_key)
);

CREATE TABLE IF NOT EXISTS historical_insights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER REFERENCES historical_reports(id) ON DELETE CASCADE,
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

CREATE TABLE IF NOT EXISTS historical_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER REFERENCES historical_reports(id) ON DELETE CASCADE,
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

CREATE TABLE IF NOT EXISTS historical_monthly_load (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER REFERENCES historical_reports(id) ON DELETE CASCADE,
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

CREATE TABLE IF NOT EXISTS historical_fault_heatmap (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER REFERENCES historical_reports(id) ON DELETE CASCADE,
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

CREATE TABLE IF NOT EXISTS historical_import_runs (
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

CREATE INDEX IF NOT EXISTS idx_historical_reports_period
    ON historical_reports(period_start, period_end);
CREATE INDEX IF NOT EXISTS idx_historical_kpis_metric
    ON historical_kpis(metric_type, period_start);
CREATE INDEX IF NOT EXISTS idx_historical_machine_period
    ON historical_machine_metrics(machine_key, period_start);
CREATE INDEX IF NOT EXISTS idx_historical_fault_family
    ON historical_fault_families(fault_family, machine_key);
CREATE INDEX IF NOT EXISTS idx_historical_actions_status
    ON historical_action_plan(status, priority);
CREATE INDEX IF NOT EXISTS idx_historical_events_time
    ON historical_events(event_at, machine_key);
CREATE INDEX IF NOT EXISTS idx_historical_monthly_machine
    ON historical_monthly_load(month_start, machine_key);
CREATE INDEX IF NOT EXISTS idx_historical_heatmap
    ON historical_fault_heatmap(department, machine_key, fault_family);
