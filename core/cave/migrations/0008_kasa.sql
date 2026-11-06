-- Kasa devices an Admin added. mac is the stable identity: a plug's address can change.
CREATE TABLE kasa_devices (
    mac TEXT PRIMARY KEY,
    host TEXT NOT NULL,
    model TEXT NOT NULL,
    kind TEXT NOT NULL,
    name TEXT NOT NULL
);

-- Hashes of the TP-Link sign-in, which is all the plugs need. The password itself is never stored.
CREATE TABLE kasa_login (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    hash_v2 BLOB NOT NULL,
    hash_v1 BLOB NOT NULL
);
