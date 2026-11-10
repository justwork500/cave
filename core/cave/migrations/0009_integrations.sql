-- Secrets CAVE must read back (pairing keys, passwords). AES-GCM under the host key, never plain text.
CREATE TABLE credentials (
    integration TEXT NOT NULL,
    name TEXT NOT NULL,
    nonce BLOB NOT NULL,
    ciphertext BLOB NOT NULL,
    PRIMARY KEY (integration, name)
);

-- Devices an Admin added through any Phase 2 integration. device_id is the MAC or serial: an address can change.
CREATE TABLE integration_devices (
    integration TEXT NOT NULL,
    device_id TEXT NOT NULL,
    host TEXT NOT NULL,
    model TEXT NOT NULL,
    name TEXT NOT NULL,
    settings TEXT NOT NULL DEFAULT '{}',  -- JSON, never secrets
    PRIMARY KEY (integration, device_id)
);
