CREATE TABLE setup_code (
    code_hash TEXT NOT NULL
);
CREATE TABLE areas (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    floor TEXT
);
CREATE TABLE entity_overrides (
    entity_id TEXT PRIMARY KEY,
    name TEXT,
    area_id TEXT REFERENCES areas(id) ON DELETE SET NULL
);
