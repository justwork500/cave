import sqlite3
from dataclasses import asdict

from cave import audit
from cave.access.model import Item, ItemKind, TargetKind
from cave.db import Database

BUILTIN_SECTIONS = {
    "section:devices": "Devices",
    "section:automations": "Automations",
    "section:scripts": "Scripts",
    "section:dashboards": "Dashboards",
    "section:users": "Users and permissions",
    "section:system": "System",
    "section:audit": "Audit log",
    "section:signin_log": "Sign-in log",
    "section:run_history": "Run history",
}
BUILTIN_FEATURES = {"feature:test_center": "Use the Test Center", "feature:api_tokens": "Create API tokens"}
BUILTIN_DASHBOARDS = {"dashboard:home": "Home"}
STARTING_ASSIGNMENTS: dict[str, list[tuple[TargetKind, str]]] = {
    "section:devices": [("role", "operator")],
    "section:automations": [("role", "operator")],
    "section:scripts": [("role", "operator")],
    "section:dashboards": [("role", "operator")],
    "feature:test_center": [("role", "operator")],
    "dashboard:home": [("role", "household")],
    "section:audit": [("role", "auditor")],
    "section:signin_log": [("role", "auditor")],
    "section:run_history": [("role", "auditor")],
}


def _to_item(row: sqlite3.Row) -> Item:
    return Item(
        id=row["id"],
        kind=row["kind"],
        name=row["name"],
        status=row["status"],
        visibility=row["visibility"],
        others_see=row["others_see"],
        network=row["network"],
        builtin=bool(row["builtin"]),
    )


def get_item(db: Database, item_id: str) -> Item | None:
    row = db.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    return _to_item(row) if row else None


def list_items(db: Database) -> list[Item]:
    return [_to_item(r) for r in db.execute("SELECT * FROM items ORDER BY kind, name").fetchall()]


def upsert_item(db: Database, actor: str, item: Item) -> None:
    old = get_item(db, item.id)
    db.execute(
        "INSERT INTO items (id, kind, name, status, visibility, others_see, network, builtin) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET kind=excluded.kind, name=excluded.name, "
        "status=excluded.status, visibility=excluded.visibility, others_see=excluded.others_see, "
        "network=excluded.network, builtin=excluded.builtin",
        (item.id, item.kind, item.name, item.status, item.visibility, item.others_see, item.network, int(item.builtin)),
    )
    if old != item:
        action = "item.create" if old is None else "item.update"
        audit.record(db, actor, action, f"item:{item.id}", asdict(old) if old else None, asdict(item))


def get_assignments(db: Database, item_id: str) -> list[tuple[TargetKind, str]]:
    rows = db.execute(
        "SELECT target_kind, target_id FROM assignments WHERE item_id=? ORDER BY target_kind, target_id", (item_id,)
    ).fetchall()
    return [(r["target_kind"], r["target_id"]) for r in rows]


def set_assignments(db: Database, actor: str, item_id: str, targets: list[tuple[TargetKind, str]]) -> None:
    old = get_assignments(db, item_id)
    with db.transaction() as conn:
        conn.execute("DELETE FROM assignments WHERE item_id=?", (item_id,))
        conn.executemany(
            "INSERT OR IGNORE INTO assignments (item_id, target_kind, target_id) VALUES (?, ?, ?)",
            [(item_id, k, t) for k, t in targets],
        )
    new = get_assignments(db, item_id)
    if old != new:
        audit.record(db, actor, "item.assignments", f"item:{item_id}", [list(a) for a in old], [list(a) for a in new])


def set_item_entities(db: Database, item_id: str, entity_ids: list[str]) -> None:
    with db.transaction() as conn:
        conn.execute("DELETE FROM item_entities WHERE item_id=?", (item_id,))
        conn.executemany(
            "INSERT OR IGNORE INTO item_entities (item_id, entity_id) VALUES (?, ?)",
            [(item_id, e) for e in entity_ids],
        )


def items_containing(db: Database, entity_id: str) -> list[str]:
    rows = db.execute("SELECT item_id FROM item_entities WHERE entity_id=?", (entity_id,)).fetchall()
    return [r["item_id"] for r in rows]


def seed_builtins(db: Database) -> None:
    """Create built-in items once. Never overwrites what an Admin has changed since."""
    groups: list[tuple[ItemKind, dict[str, str]]] = [
        ("section", BUILTIN_SECTIONS),
        ("feature", BUILTIN_FEATURES),
        ("dashboard", BUILTIN_DASHBOARDS),
    ]
    for kind, names in groups:
        for item_id, name in names.items():
            if get_item(db, item_id) is None:
                upsert_item(db, "system", Item(item_id, kind, name, others_see="none", builtin=True))
                set_assignments(db, "system", item_id, STARTING_ASSIGNMENTS.get(item_id, []))
