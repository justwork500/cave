"""notify.cave: the console's notification bell. Phase 1's only notify target."""

from datetime import UTC, datetime
from typing import Any

from cave.db import Database
from cave.state import EventBus

MAX_TITLE = 120
MAX_MESSAGE = 2000


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _enabled(db: Database, user_ids: list[str]) -> list[str]:
    now = datetime.now(UTC).isoformat()
    out = []
    for uid in user_ids:
        row = db.execute(
            "SELECT 1 FROM users WHERE id=? AND enabled=1 AND (expires_at IS NULL OR expires_at>?)", (uid, now)
        ).fetchone()
        if row:
            out.append(uid)
    return out


def recipients(db: Database, targets: list[str], item_id: str) -> list[str]:
    """user:<name> targets; otherwise whoever last saved the automation; otherwise every Admin."""
    names = [t.split(":", 1)[1] for t in targets if t.startswith("user:")]
    if names:
        ids = [r["id"] for n in names for r in db.execute("SELECT id FROM users WHERE username=?", (n,)).fetchall()]
        return _enabled(db, ids)
    saver = db.execute("SELECT user_id FROM config_saves WHERE item_id=?", (item_id,)).fetchone()
    if saver and saver["user_id"] and (ids := _enabled(db, [saver["user_id"]])):
        return ids
    admins = db.execute("SELECT id FROM users WHERE role='admin' ORDER BY username").fetchall()
    return _enabled(db, [r["id"] for r in admins])


def create(db: Database, bus: EventBus, user_ids: list[str], title: str | None, message: str, source: str) -> None:
    title = _cut(title, MAX_TITLE) if title else None
    message = _cut(message, MAX_MESSAGE)
    now = datetime.now(UTC).isoformat()
    for uid in user_ids:
        cur = db.execute(
            "INSERT INTO notifications (user_id, title, message, source, created_at) VALUES (?, ?, ?, ?, ?)",
            (uid, title, message, source, now),
        )
        bus.publish({"type": "notification", "user_id": uid, "id": cur.lastrowid, "title": title,
                     "message": message})


def list_for(db: Database, user_id: str, unread_only: bool) -> list[dict[str, Any]]:
    sql = "SELECT id, title, message, source, created_at, read_at FROM notifications WHERE user_id=?"
    if unread_only:
        sql += " AND read_at IS NULL"
    return [dict(r) for r in db.execute(sql + " ORDER BY id DESC LIMIT 200", (user_id,)).fetchall()]


def mark_read(db: Database, user_id: str, ids: list[int]) -> None:
    now = datetime.now(UTC).isoformat()
    for i in ids:
        db.execute(
            "UPDATE notifications SET read_at=? WHERE user_id=? AND id=? AND read_at IS NULL", (now, user_id, i)
        )
