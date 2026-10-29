CREATE TABLE config_files (
    path TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL,
    loaded_at TEXT NOT NULL
);
CREATE TABLE config_saves (
    item_id TEXT PRIMARY KEY,
    user_id TEXT,
    saved_at TEXT NOT NULL
);
CREATE TABLE automation_traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id TEXT NOT NULL,
    test INTEGER NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    outcome TEXT,
    trace TEXT
);
CREATE INDEX automation_traces_item ON automation_traces(item_id, test, id);
CREATE TABLE notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT,
    message TEXT NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    read_at TEXT
);
CREATE INDEX notifications_user ON notifications(user_id, id);
