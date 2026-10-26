import hashlib
import secrets
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

import pyotp

from cave import audit
from cave.auth.passwords import DUMMY_HASH, hash_password, verify_password
from cave.db import Database

Role = Literal["admin", "operator", "household", "guest", "auditor"]

LOCKOUT_ATTEMPTS = 5
LOCKOUT_WINDOW = timedelta(minutes=15)
RECOVERY_CODE_COUNT = 10


@dataclass(frozen=True)
class User:
    id: str
    username: str
    display_name: str
    role: Role
    enabled: bool
    expires_at: datetime | None
    has_totp: bool


class LoginError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _to_user(row: sqlite3.Row) -> User:
    return User(
        id=row["id"],
        username=row["username"],
        display_name=row["display_name"],
        role=row["role"],
        enabled=bool(row["enabled"]),
        expires_at=datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None,
        has_totp=row["totp_secret"] is not None,
    )


def create_user(db: Database, actor: str, username: str, password: str, role: Role, display_name: str = "") -> User:
    user_id = uuid.uuid4().hex
    db.execute(
        "INSERT INTO users (id, username, display_name, role, password_hash, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, username, display_name or username, role, hash_password(password), datetime.now(UTC).isoformat()),
    )
    audit.record(db, actor, "user.create", f"user:{user_id}", None, {"username": username, "role": role})
    user = get_user(db, user_id)
    assert user is not None
    return user


def get_user(db: Database, user_id: str) -> User | None:
    row = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return _to_user(row) if row else None


def is_active(user: User, now: datetime) -> bool:
    return user.enabled and (user.expires_at is None or user.expires_at > now)


def _recent_failures(db: Database, username: str, now: datetime) -> int:
    since = (now - LOCKOUT_WINDOW).isoformat()
    last_ok = db.execute(
        "SELECT max(at) FROM login_attempts WHERE username=? AND ok=1", (username,)
    ).fetchone()[0]
    since = max(since, last_ok) if last_ok else since
    return int(
        db.execute(
            "SELECT count(*) FROM login_attempts WHERE username=? AND ok=0 AND at>? AND at<=?",
            (username, since, now.isoformat()),
        ).fetchone()[0]
    )


def check_password(db: Database, username: str, password: str, ip: str, now: datetime) -> User:
    def log(ok: bool) -> None:
        db.execute(
            "INSERT INTO login_attempts (username, at, ok, ip) VALUES (?, ?, ?, ?)",
            (username, now.isoformat(), int(ok), ip),
        )

    if _recent_failures(db, username, now) >= LOCKOUT_ATTEMPTS:
        log(False)
        raise LoginError("Too many attempts. Try again in 15 minutes.")
    row = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    ok = verify_password(row["password_hash"] if row else DUMMY_HASH, password)
    user = _to_user(row) if row else None
    if not ok or user is None or not is_active(user, now):
        log(False)
        raise LoginError("Wrong username or password.")
    log(True)
    return user


def mfa_required(user: User | None) -> bool:
    return user is not None and (user.role in ("admin", "operator") or user.has_totp)


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.strip().lower().encode()).hexdigest()


def setup_totp(db: Database, user_id: str) -> tuple[str, list[str]]:
    secret = pyotp.random_base32()
    codes = [f"{secrets.token_hex(4)}-{secrets.token_hex(4)}" for _ in range(RECOVERY_CODE_COUNT)]
    user = get_user(db, user_id)
    assert user is not None
    with db.transaction() as conn:
        # shortcut: TOTP secret stored unencrypted in the DB; encrypt with a host key when secrets storage lands
        conn.execute("UPDATE users SET totp_secret=? WHERE id=?", (secret, user_id))
        conn.execute("DELETE FROM recovery_codes WHERE user_id=?", (user_id,))
        conn.executemany(
            "INSERT INTO recovery_codes (user_id, code_hash) VALUES (?, ?)",
            [(user_id, _hash_code(c)) for c in codes],
        )
    audit.record(db, f"user:{user_id}", "user.mfa_setup", f"user:{user_id}")
    return pyotp.TOTP(secret).provisioning_uri(name=user.username, issuer_name="CAVE"), codes


def verify_second_factor(db: Database, user_id: str, code: str) -> bool:
    row = db.execute("SELECT totp_secret FROM users WHERE id=?", (user_id,)).fetchone()
    if not row or not row["totp_secret"]:
        return False
    if code.isdigit() and pyotp.TOTP(row["totp_secret"]).verify(code, valid_window=1):
        return True
    cur = db.execute(
        "UPDATE recovery_codes SET used_at=? WHERE user_id=? AND code_hash=? AND used_at IS NULL",
        (datetime.now(UTC).isoformat(), user_id, _hash_code(code)),
    )
    return cur.rowcount == 1


class LastAdminError(Exception):
    pass


def list_users(db: Database) -> list[User]:
    return [_to_user(r) for r in db.execute("SELECT * FROM users ORDER BY username").fetchall()]


def update_user(
    db: Database,
    actor: str,
    user_id: str,
    *,
    display_name: str | None = None,
    role: Role | None = None,
    enabled: bool | None = None,
    expires_at: datetime | None = None,
) -> User:
    """Change a user. Refuses to leave CAVE without an enabled Admin."""
    old = get_user(db, user_id)
    if old is None:
        raise KeyError(user_id)
    new_role = role or old.role
    new_enabled = old.enabled if enabled is None else enabled
    new_expiry = expires_at or old.expires_at  # shortcut: no way to clear an expiry yet; add when the UI needs it
    with db.transaction() as conn:
        if old.role == "admin" and old.enabled and (new_role != "admin" or not new_enabled):
            others = conn.execute(
                "SELECT count(*) FROM users WHERE role='admin' AND enabled=1 AND id<>?", (user_id,)
            ).fetchone()[0]
            if others == 0:
                raise LastAdminError("CAVE needs at least one enabled Admin.")
        conn.execute(
            "UPDATE users SET display_name=?, role=?, enabled=?, expires_at=? WHERE id=?",
            (
                old.display_name if display_name is None else display_name,
                new_role,
                int(new_enabled),
                new_expiry.isoformat() if new_expiry else None,
                user_id,
            ),
        )
    new = get_user(db, user_id)
    assert new is not None
    fields = ("display_name", "role", "enabled", "expires_at")
    audit.record(
        db, actor, "user.update", f"user:{user_id}",
        {f: str(getattr(old, f)) for f in fields}, {f: str(getattr(new, f)) for f in fields},
    )
    return new
