import hashlib
import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

from cave import audit
from cave.db import Database

PREFIX = "cave_"


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def create(db: Database, actor: str, user_id: str, name: str) -> str:
    """Returns the raw token once. Only its SHA-256 is stored."""
    raw = PREFIX + secrets.token_urlsafe(32)
    token_id = uuid.uuid4().hex
    db.execute(
        "INSERT INTO api_tokens (id, user_id, name, token_hash, created_at) VALUES (?, ?, ?, ?, ?)",
        (token_id, user_id, name, _hash(raw), datetime.now(UTC).isoformat()),
    )
    audit.record(db, actor, "token.create", f"token:{token_id}", None, {"user_id": user_id, "name": name})
    return raw


def lookup(db: Database, raw: str) -> tuple[str, str] | None:
    """(token_id, owner user_id) for a live token."""
    row = db.execute(
        "SELECT id, user_id FROM api_tokens WHERE token_hash=? AND revoked_at IS NULL", (_hash(raw),)
    ).fetchone()
    return (row["id"], row["user_id"]) if row else None


def list_tokens(db: Database, user_id: str | None) -> list[dict[str, Any]]:
    """Live tokens for one user, or for everyone when user_id is None. Never includes the token itself."""
    sql = "SELECT id, user_id, name, created_at FROM api_tokens WHERE revoked_at IS NULL"
    rows = db.execute(sql + " AND user_id=?", (user_id,)) if user_id else db.execute(sql)
    return [dict(r) for r in rows.fetchall()]


def revoke(db: Database, actor: str, token_id: str) -> None:
    db.execute("UPDATE api_tokens SET revoked_at=? WHERE id=?", (datetime.now(UTC).isoformat(), token_id))
    audit.record(db, actor, "token.revoke", f"token:{token_id}")
