"""Device passwords and pairing keys CAVE must read back: AES-GCM under a host key, never plain text."""

import logging
import os
import re
from collections.abc import Mapping
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from cave import audit
from cave.db import Database
from cave.envconfig import env_secret

log = logging.getLogger(__name__)
_HEX64 = re.compile(r"[0-9a-f]{64}")


def load_host_key(db_path: Path, environ: Mapping[str, str] = os.environ) -> bytes:
    """CAVE_HOST_KEY(_FILE), else host_key beside the database (made on first start). Errors never show the value."""
    value = env_secret("CAVE_HOST_KEY", environ)
    if value is not None:
        if not _HEX64.fullmatch(value):
            raise SystemExit("CAVE_HOST_KEY must be 64 hex characters (32 random bytes).")
        return bytes.fromhex(value)
    path = db_path.parent / "host_key"
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        text = path.read_text(encoding="utf-8").strip()
        if not _HEX64.fullmatch(text):
            raise SystemExit(f"{path} must hold 64 hex characters (32 random bytes).") from None
        return bytes.fromhex(text)
    key = os.urandom(32)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(key.hex())
    return key


class Credentials:
    def __init__(self, db: Database, key: bytes) -> None:
        self._db = db
        self._aes = AESGCM(key)

    @staticmethod
    def _aad(integration: str, name: str) -> bytes:  # binds a row to its name, so rows can't be swapped
        return f"{integration}:{name}".encode()

    def is_set(self, integration: str, name: str) -> bool:
        return self.get(integration, name) is not None

    def set(self, integration: str, name: str, value: str, actor: str) -> None:
        old = self.is_set(integration, name)
        nonce = os.urandom(12)
        ct = self._aes.encrypt(nonce, value.encode(), self._aad(integration, name))
        self._db.execute("INSERT OR REPLACE INTO credentials (integration, name, nonce, ciphertext) VALUES (?, ?, ?, ?)",
                         (integration, name, nonce, ct))
        audit.record(self._db, actor, "credential.set", f"credential:{integration}:{name}", {"set": old}, {"set": True})

    def get(self, integration: str, name: str) -> str | None:
        row = self._db.execute("SELECT nonce, ciphertext FROM credentials WHERE integration = ? AND name = ?",
                               (integration, name)).fetchone()
        if row is None:
            return None
        try:
            return self._aes.decrypt(row["nonce"], row["ciphertext"], self._aad(integration, name)).decode()
        except InvalidTag:
            log.warning("Credential %s:%s can't be decrypted (wrong host key?); treating it as not set.",
                        integration, name)
            return None

    def delete(self, integration: str, name: str, actor: str) -> None:
        old = self.is_set(integration, name)
        self._db.execute("DELETE FROM credentials WHERE integration = ? AND name = ?", (integration, name))
        audit.record(self._db, actor, "credential.delete", f"credential:{integration}:{name}",
                     {"set": old}, {"set": False})

    def delete_prefix(self, integration: str, prefix: str, actor: str) -> None:
        rows = self._db.execute("SELECT name FROM credentials WHERE integration = ?", (integration,)).fetchall()
        for r in rows:
            if r["name"].startswith(prefix):
                self.delete(integration, r["name"], actor)
