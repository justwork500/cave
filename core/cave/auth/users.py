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
