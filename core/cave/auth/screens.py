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

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

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


CHALLENGE_TTL = timedelta(seconds=60)
SESSION_MAX_AGE = timedelta(hours=12)
SIGNIN_FAILED = "Screen sign-in failed."


def issue_challenge(db: Database, screen_id: str, now: datetime) -> str:
    screen = get_screen(db, screen_id)
    if screen is None or screen.status != "approved":
        raise EnrollError("This screen isn't approved.")
    nonce = secrets.token_urlsafe(32)
    db.execute("DELETE FROM screen_challenges WHERE expires_at<?", (now.isoformat(),))
    db.execute(
        "INSERT INTO screen_challenges (nonce, screen_id, expires_at) VALUES (?, ?, ?)",
        (nonce, screen_id, (now + CHALLENGE_TTL).isoformat()),
    )
    return nonce


def _p1363_to_der(signature_b64: str) -> bytes:
    """WebCrypto signs ECDSA as raw r||s; cryptography verifies DER."""
    raw = base64.b64decode(signature_b64, validate=True)
    if len(raw) != 64:
        raise ValueError("not a P-256 P1363 signature")
    return encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))


def verify_challenge(db: Database, screen_id: str, nonce: str, signature_b64: str, now: datetime) -> str:
    """Returns a new screen session id. The challenge is used up whether or not this succeeds."""
    with db.transaction() as conn:
        row = conn.execute("SELECT screen_id, expires_at FROM screen_challenges WHERE nonce=?", (nonce,)).fetchone()
        conn.execute("DELETE FROM screen_challenges WHERE nonce=?", (nonce,))
    if row is None or row["screen_id"] != screen_id or datetime.fromisoformat(row["expires_at"]) < now:
        raise EnrollError(SIGNIN_FAILED)
    key_row = db.execute("SELECT public_key FROM screens WHERE id=? AND status='approved'", (screen_id,)).fetchone()
    if key_row is None or key_row["public_key"] is None:
        raise EnrollError(SIGNIN_FAILED)
    key = serialization.load_der_public_key(base64.b64decode(key_row["public_key"]))
    assert isinstance(key, ec.EllipticCurvePublicKey)
    try:
        key.verify(
            _p1363_to_der(signature_b64), f"cave-screen-auth:{screen_id}:{nonce}".encode(), ec.ECDSA(hashes.SHA256())
        )
    except (InvalidSignature, ValueError, binascii.Error) as e:
        raise EnrollError(SIGNIN_FAILED) from e
    session_id = secrets.token_urlsafe(32)
    db.execute(
        "INSERT INTO screen_sessions (id, screen_id, created_at) VALUES (?, ?, ?)",
        (session_id, screen_id, now.isoformat()),
    )
    return session_id


def screen_from_session(db: Database, session_id: str, now: datetime) -> Screen | None:
    row = db.execute("SELECT screen_id, created_at FROM screen_sessions WHERE id=?", (session_id,)).fetchone()
    if row is None:
        return None
    if datetime.fromisoformat(row["created_at"]) + SESSION_MAX_AGE < now:
        db.execute("DELETE FROM screen_sessions WHERE id=?", (session_id,))
        return None
    screen = get_screen(db, row["screen_id"])
    return screen if screen is not None and screen.status == "approved" else None


def end_session(db: Database, session_id: str) -> None:
    db.execute("DELETE FROM screen_sessions WHERE id=?", (session_id,))
