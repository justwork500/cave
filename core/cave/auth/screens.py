"""Screens: wall tablets that sign in as themselves with a key their browser can't export."""

import base64
import binascii
import hashlib
import secrets
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from cave import audit
from cave.db import Database
from cave.tls import format_fingerprint

ScreenStatus = Literal["awaiting_key", "pending", "approved", "revoked"]
ENROLL_TTL = timedelta(minutes=10)


@dataclass(frozen=True)
class Screen:
    id: str
    name: str
    status: ScreenStatus
    fingerprint: str | None
    created_at: datetime


class EnrollError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _to_screen(row: sqlite3.Row) -> Screen:
    return Screen(row["id"], row["name"], row["status"], row["fingerprint"], datetime.fromisoformat(row["created_at"]))


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def get_screen(db: Database, screen_id: str) -> Screen | None:
    row = db.execute("SELECT * FROM screens WHERE id=?", (screen_id,)).fetchone()
    return _to_screen(row) if row else None


def list_screens(db: Database) -> list[Screen]:
    return [_to_screen(r) for r in db.execute("SELECT * FROM screens ORDER BY name").fetchall()]


def create(db: Database, actor: str, name: str, now: datetime, screen_id: str | None = None) -> tuple[Screen, str]:
    """A new screen waiting for its key, plus the one-time enrollment code (shown once, stored hashed)."""
    sid = screen_id or uuid.uuid4().hex
    code = secrets.token_urlsafe(32)
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO screens (id, name, status, created_at) VALUES (?, ?, 'awaiting_key', ?)",
            (sid, name, now.isoformat()),
        )
        conn.execute(
            "INSERT INTO enrollment_codes (code_hash, screen_id, expires_at) VALUES (?, ?, ?)",
            (_hash(code), sid, (now + ENROLL_TTL).isoformat()),
        )
    audit.record(db, actor, "screen.create", f"screen:{sid}", None, {"name": name})
    screen = get_screen(db, sid)
    assert screen is not None
    return screen, code


def _load_p256(public_key_spki_b64: str) -> bytes:
    try:
        der = base64.b64decode(public_key_spki_b64, validate=True)
        key = serialization.load_der_public_key(der)
    except (ValueError, binascii.Error) as e:
        raise EnrollError("This browser's key isn't supported.") from e
    if not isinstance(key, ec.EllipticCurvePublicKey) or key.curve.name != "secp256r1":
        raise EnrollError("This browser's key isn't supported.")
    return der


def enroll(db: Database, code: str, public_key_spki_b64: str, now: datetime) -> Screen:
    expired = EnrollError("This enrollment link has expired. Ask an Admin for a new one.")
    der = _load_p256(public_key_spki_b64)
    with db.transaction() as conn:
        row = conn.execute(
            "SELECT screen_id, expires_at, used_at FROM enrollment_codes WHERE code_hash=?", (_hash(code),)
        ).fetchone()
        if row is None or row["used_at"] or datetime.fromisoformat(row["expires_at"]) < now:
            raise expired
        sid = row["screen_id"]
        status = conn.execute("SELECT status FROM screens WHERE id=?", (sid,)).fetchone()
        if status is None or status["status"] != "awaiting_key":
            raise expired
        conn.execute("UPDATE enrollment_codes SET used_at=? WHERE code_hash=?", (now.isoformat(), _hash(code)))
        conn.execute(
            "UPDATE screens SET public_key=?, fingerprint=?, status='pending' WHERE id=?",
            (base64.b64encode(der).decode(), format_fingerprint(hashlib.sha256(der).digest()), sid),
        )
    screen = get_screen(db, sid)
    assert screen is not None
    audit.record(db, f"screen:{sid}", "screen.enroll", f"screen:{sid}", None, {"fingerprint": screen.fingerprint})
    return screen


class ScreenStateError(Exception):
    pass


def approve(db: Database, actor: str, screen_id: str, now: datetime) -> Screen:
    cur = db.execute(
        "UPDATE screens SET status='approved', approved_by=?, approved_at=? WHERE id=? AND status='pending'",
        (actor, now.isoformat(), screen_id),
    )
    if cur.rowcount != 1:
        raise ScreenStateError("Only a screen waiting for approval can be approved.")
    audit.record(db, actor, "screen.approve", f"screen:{screen_id}", {"status": "pending"}, {"status": "approved"})
    screen = get_screen(db, screen_id)
    assert screen is not None
    return screen


def revoke(db: Database, actor: str, screen_id: str) -> Screen:
    old = get_screen(db, screen_id)
    if old is None:
        raise KeyError(screen_id)
    with db.transaction() as conn:
        conn.execute("UPDATE screens SET status='revoked', public_key=NULL WHERE id=?", (screen_id,))
        conn.execute("DELETE FROM screen_sessions WHERE screen_id=?", (screen_id,))
        conn.execute("DELETE FROM screen_challenges WHERE screen_id=?", (screen_id,))
        conn.execute("DELETE FROM enrollment_codes WHERE screen_id=?", (screen_id,))
    audit.record(db, actor, "screen.revoke", f"screen:{screen_id}", {"status": old.status}, {"status": "revoked"})
    screen = get_screen(db, screen_id)
    assert screen is not None
    return screen
