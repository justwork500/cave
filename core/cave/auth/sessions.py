"""Browser sessions: create, look up and end them."""

import secrets
from datetime import datetime, timedelta

from cave.db import Database


def create(db: Database, user_id: str, now: datetime) -> str:
    session_id = secrets.token_urlsafe(32)
    db.execute(
        "INSERT INTO sessions (id, user_id, created_at, last_seen) VALUES (?, ?, ?, ?)",
        (session_id, user_id, now.isoformat(), now.isoformat()),
    )
    return session_id


def lookup(db: Database, session_id: str, now: datetime, idle: timedelta) -> str | None:
    row = db.execute("SELECT user_id, last_seen FROM sessions WHERE id=?", (session_id,)).fetchone()
    if row is None:
        return None
    if datetime.fromisoformat(row["last_seen"]) + idle < now:
        end(db, session_id)
        return None
    db.execute("UPDATE sessions SET last_seen=? WHERE id=?", (now.isoformat(), session_id))
    return str(row["user_id"])


def end(db: Database, session_id: str) -> None:
    db.execute("DELETE FROM sessions WHERE id=?", (session_id,))


def end_for_user(db: Database, user_id: str) -> None:
    db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))


def end_others(db: Database, user_id: str, keep: str) -> None:
    db.execute("DELETE FROM sessions WHERE user_id=? AND id<>?", (user_id, keep))
