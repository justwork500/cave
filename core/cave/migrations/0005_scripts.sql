CREATE TABLE script_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    script TEXT NOT NULL,
    started_by TEXT NOT NULL,
    target TEXT NOT NULL,
    params TEXT NOT NULL,
    started_at TEXT NOT NULL,
    duration_ms INTEGER,
    exit_code INTEGER,
    outcome TEXT NOT NULL,
    log TEXT NOT NULL,
    result TEXT
);
CREATE INDEX script_runs_script ON script_runs(script, id);
