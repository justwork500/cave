CREATE TABLE users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    display_name TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL CHECK (role IN ('admin', 'operator', 'household', 'guest', 'auditor')),
    enabled INTEGER NOT NULL DEFAULT 1,
    expires_at TEXT,
    password_hash TEXT NOT NULL,
    totp_secret TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE recovery_codes (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    code_hash TEXT NOT NULL,
    used_at TEXT
);
CREATE TABLE login_attempts (
    username TEXT NOT NULL COLLATE NOCASE,
    at TEXT NOT NULL,
    ok INTEGER NOT NULL,
    ip TEXT NOT NULL
);
CREATE INDEX login_attempts_user ON login_attempts(username, at);
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    last_seen TEXT NOT NULL
);
CREATE TABLE user_groups (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE
);
CREATE TABLE group_members (
    group_id TEXT NOT NULL REFERENCES user_groups(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    PRIMARY KEY (group_id, user_id)
);
CREATE TABLE items (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('dashboard', 'section', 'action', 'feature')),
    name TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('enabled', 'disabled')),
    visibility TEXT NOT NULL CHECK (visibility IN ('show', 'hide', 'restrict')),
    others_see TEXT NOT NULL CHECK (others_see IN ('locked', 'none')),
    network TEXT NOT NULL CHECK (network IN ('anywhere', 'local')),
    builtin INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE assignments (
    item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    target_kind TEXT NOT NULL CHECK (target_kind IN ('user', 'group', 'role', 'screen')),
    target_id TEXT NOT NULL,
    PRIMARY KEY (item_id, target_kind, target_id)
);
CREATE TABLE item_entities (
    item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    entity_id TEXT NOT NULL,
    PRIMARY KEY (item_id, entity_id)
);
CREATE INDEX item_entities_entity ON item_entities(entity_id);
CREATE TABLE api_tokens (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    revoked_at TEXT
);
CREATE TABLE audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    time TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    target TEXT NOT NULL,
    old TEXT,
    new TEXT
);
