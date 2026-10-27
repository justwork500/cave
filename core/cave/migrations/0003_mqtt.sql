CREATE TABLE mqtt_entities (
    unique_id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL UNIQUE,
    first_seen TEXT NOT NULL
);
