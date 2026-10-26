CREATE TABLE network_ranges (
    cidr TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('local', 'trusted_proxy')),
    PRIMARY KEY (cidr, kind)
);
CREATE TABLE screens (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('awaiting_key', 'pending', 'approved', 'revoked')),
    public_key TEXT,
    fingerprint TEXT,
    created_at TEXT NOT NULL,
    approved_by TEXT,
    approved_at TEXT
);
CREATE TABLE enrollment_codes (
    code_hash TEXT PRIMARY KEY,
    screen_id TEXT NOT NULL REFERENCES screens(id) ON DELETE CASCADE,
    expires_at TEXT NOT NULL,
    used_at TEXT
);
CREATE TABLE screen_challenges (
    nonce TEXT PRIMARY KEY,
    screen_id TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE TABLE screen_sessions (
    id TEXT PRIMARY KEY,
    screen_id TEXT NOT NULL REFERENCES screens(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL
);
