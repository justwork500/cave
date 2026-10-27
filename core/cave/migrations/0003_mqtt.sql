CREATE TABLE mqtt_entities (
    component TEXT NOT NULL,
    unique_id TEXT NOT NULL,
    entity_id TEXT NOT NULL UNIQUE,
    config_topic TEXT NOT NULL,  -- the discovery topic it belongs to, or 'manual'
    first_seen TEXT NOT NULL,
    PRIMARY KEY (component, unique_id)
);
