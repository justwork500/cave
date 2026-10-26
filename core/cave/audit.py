import json
from datetime import UTC, datetime
from typing import Any

from cave.db import Database


def record(db: Database, actor: str, action: str, target: str, old: Any = None, new: Any = None) -> None:
    db.execute(
        "INSERT INTO audit (time, actor, action, target, old, new) VALUES (?, ?, ?, ?, ?, ?)",
        (datetime.now(UTC).isoformat(), actor, action, target, json.dumps(old), json.dumps(new)),
    )


def list_entries(db: Database, limit: int = 100) -> list[dict[str, Any]]:
    rows = db.execute(
        "SELECT time, actor, action, target, old, new FROM audit ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) | {"old": json.loads(r["old"]), "new": json.loads(r["new"])} for r in rows]
