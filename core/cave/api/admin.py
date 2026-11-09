"""Admin API: users, groups, access items and their assignments, the audit log and API tokens."""

import uuid
from dataclasses import asdict, replace
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from cave import audit
from cave.access.evaluate import evaluate
from cave.access.items import get_assignments, get_item, list_items, set_assignments, upsert_item
from cave.access.model import NetworkCond, OthersSee, Principal, Purpose, Status, TargetKind, Visibility
from cave.api.deps import client_ip, current_principal, get_db, net
from cave.auth import sessions, tokens
from cave.auth.users import LastAdminError, Role, User, create_user, list_users, update_user
from cave.state import EventBus

router = APIRouter(prefix="/api/v1")
Caller = Annotated[Principal, Depends(current_principal)]
MIN_PASSWORD = 8


def _actor(p: Principal) -> str:
    return f"{p.kind}:{p.id}"


def _require(request: Request, p: Principal, item_id: str, purpose: Purpose = "manage") -> None:
    item = get_item(get_db(request), item_id)
    if item is None or not evaluate(
        get_db(request), p, item, client_ip(request), net(request).local_ranges, purpose
    ).allowed:
        raise HTTPException(403, "You don't have access to this.")


def _access_changed(request: Request) -> None:
    bus: EventBus = request.app.state.bus
    bus.publish({"type": "access_changed"})


def _user_out(u: User) -> dict[str, Any]:
    return {
        "id": u.id, "username": u.username, "display_name": u.display_name, "role": u.role,
        "enabled": u.enabled, "expires_at": u.expires_at.isoformat() if u.expires_at else None,
    }


# ---- users ----

class NewUser(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=MIN_PASSWORD)
    role: Role
    display_name: str = ""


class UserPatch(BaseModel):
    display_name: str | None = None
    role: Role | None = None
    enabled: bool | None = None
    expires_at: datetime | None = None


@router.get("/users")
def get_users(request: Request, p: Caller) -> list[dict[str, Any]]:
    _require(request, p, "section:users")
    return [_user_out(u) for u in list_users(get_db(request))]


@router.post("/users", status_code=201)
def post_user(body: NewUser, request: Request, p: Caller) -> dict[str, Any]:
    _require(request, p, "section:users")
    try:
        u = create_user(get_db(request), _actor(p), body.username, body.password, body.role, body.display_name)
    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(409, "That username is taken.") from e
        raise
    _access_changed(request)
    return _user_out(u)


@router.patch("/users/{user_id}")
def patch_user(user_id: str, body: UserPatch, request: Request, p: Caller) -> dict[str, Any]:
    _require(request, p, "section:users")
    db = get_db(request)
    try:
        u = update_user(db, _actor(p), user_id, **body.model_dump(exclude_unset=True))
    except KeyError as e:
        raise HTTPException(404, "No such user.") from e
    except LastAdminError as e:
        raise HTTPException(409, str(e)) from e
    if not u.enabled:
        sessions.end_for_user(db, user_id)
        bus: EventBus = request.app.state.bus
        bus.publish({"type": "principal_disabled", "user_id": user_id})
    _access_changed(request)
    return _user_out(u)


# ---- groups ----

class NewGroup(BaseModel):
    name: str = Field(min_length=1, max_length=64)


def _members(request: Request, group_id: str) -> list[str]:
    rows = get_db(request).execute(
        "SELECT user_id FROM group_members WHERE group_id=? ORDER BY user_id", (group_id,)
    ).fetchall()
    return [r["user_id"] for r in rows]


@router.get("/groups")
def get_groups(request: Request, p: Caller) -> list[dict[str, Any]]:
    _require(request, p, "section:users")
    rows = get_db(request).execute("SELECT id, name FROM user_groups ORDER BY name").fetchall()
    return [{"id": r["id"], "name": r["name"], "members": _members(request, r["id"])} for r in rows]


@router.post("/groups", status_code=201)
def post_group(body: NewGroup, request: Request, p: Caller) -> dict[str, Any]:
    _require(request, p, "section:users")
    group_id = uuid.uuid4().hex
    try:
        get_db(request).execute("INSERT INTO user_groups (id, name) VALUES (?, ?)", (group_id, body.name))
    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(409, "A group with that name exists.") from e
        raise
    audit.record(get_db(request), _actor(p), "group.create", f"group:{group_id}", None, {"name": body.name})
    return {"id": group_id, "name": body.name, "members": []}


@router.put("/groups/{group_id}/members")
def put_members(group_id: str, members: list[str], request: Request, p: Caller) -> dict[str, Any]:
    _require(request, p, "section:users")
    db = get_db(request)
    if db.execute("SELECT 1 FROM user_groups WHERE id=?", (group_id,)).fetchone() is None:
        raise HTTPException(404, "No such group.")
    old = _members(request, group_id)
    try:
        with db.transaction() as conn:
            conn.execute("DELETE FROM group_members WHERE group_id=?", (group_id,))
            conn.executemany(
                "INSERT OR IGNORE INTO group_members (group_id, user_id) VALUES (?, ?)",
                [(group_id, m) for m in members],
            )
    except Exception as e:
        if "FOREIGN KEY" in str(e):
            raise HTTPException(422, "One of those users doesn't exist.") from e
        raise
    new = _members(request, group_id)
    audit.record(db, _actor(p), "group.members", f"group:{group_id}", old, new)
    _access_changed(request)
    return {"id": group_id, "members": new}


@router.delete("/groups/{group_id}", status_code=204)
def delete_group(group_id: str, request: Request, p: Caller) -> None:
    _require(request, p, "section:users")
    db = get_db(request)
    row = db.execute("SELECT name FROM user_groups WHERE id=?", (group_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "No such group.")
    with db.transaction() as conn:
        conn.execute("DELETE FROM assignments WHERE target_kind='group' AND target_id=?", (group_id,))
        conn.execute("DELETE FROM user_groups WHERE id=?", (group_id,))
    audit.record(db, _actor(p), "group.delete", f"group:{group_id}", {"name": row["name"]}, None)
    _access_changed(request)


# ---- items and assignments ----

class ItemPatch(BaseModel):
    status: Status | None = None
    visibility: Visibility | None = None
    others_see: OthersSee | None = None
    network: NetworkCond | None = None


class Assignment(BaseModel):
    kind: TargetKind
    id: str = Field(min_length=1)


@router.get("/items")
def get_items(request: Request, p: Caller) -> list[dict[str, Any]]:
    db, ip, ranges = get_db(request), client_ip(request), net(request).local_ranges
    config = request.app.state.config
    out = []
    for item in list_items(db):
        d = evaluate(db, p, item, ip, ranges)
        if d.listed:
            out.append({"id": item.id, "kind": item.kind, "name": item.name, "allowed": d.allowed} | (
                # a deleted dashboard keeps its item and access settings; menus leave it out
                {"missing": config.get("dashboard", item.id.removeprefix("dashboard:")) is None}
                if item.kind == "dashboard" else {}
            ) | (
                {"status": item.status, "visibility": item.visibility, "others_see": item.others_see,
                 "network": item.network, "builtin": item.builtin} if p.is_admin else {}
            ))
    return out


@router.patch("/items/{item_id}")
def patch_item(item_id: str, body: ItemPatch, request: Request, p: Caller) -> dict[str, Any]:
    _require(request, p, "section:users")
    db = get_db(request)
    item = get_item(db, item_id)
    if item is None:
        raise HTTPException(404, "No such item.")
    updated = replace(item, **body.model_dump(exclude_unset=True, exclude_none=True))
    upsert_item(db, _actor(p), updated)
    _access_changed(request)
    return asdict(updated)


@router.get("/items/{item_id}/assignments")
def get_item_assignments(item_id: str, request: Request, p: Caller) -> list[dict[str, str]]:
    _require(request, p, "section:users")
    return [{"kind": k, "id": t} for k, t in get_assignments(get_db(request), item_id)]


@router.put("/items/{item_id}/assignments")
def put_item_assignments(
    item_id: str, body: list[Assignment], request: Request, p: Caller
) -> list[dict[str, str]]:
    _require(request, p, "section:users")
    db = get_db(request)
    if get_item(db, item_id) is None:
        raise HTTPException(404, "No such item.")
    set_assignments(db, _actor(p), item_id, [(a.kind, a.id) for a in body])
    _access_changed(request)
    return [{"kind": k, "id": t} for k, t in get_assignments(db, item_id)]


# ---- audit ----

@router.get("/audit")
def get_audit(request: Request, p: Caller, limit: int = 100) -> list[dict[str, Any]]:
    _require(request, p, "section:audit", "use")
    return audit.list_entries(get_db(request), min(max(limit, 1), 1000))


# ---- API tokens ----

class NewToken(BaseModel):
    name: str = Field(min_length=1, max_length=64)


@router.post("/tokens", status_code=201)
def post_token(body: NewToken, request: Request, p: Caller) -> dict[str, str]:
    if p.kind == "token":
        raise HTTPException(403, "An API token can't create more tokens.")
    _require(request, p, "feature:api_tokens", "use")
    assert p.user_id is not None
    return {"token": tokens.create(get_db(request), _actor(p), p.user_id, body.name)}


@router.get("/tokens")
def get_tokens(request: Request, p: Caller) -> list[dict[str, Any]]:
    return tokens.list_tokens(get_db(request), None if p.is_admin else p.user_id)


@router.delete("/tokens/{token_id}", status_code=204)
def delete_token(token_id: str, request: Request, p: Caller) -> None:
    mine = {t["id"] for t in tokens.list_tokens(get_db(request), None if p.is_admin else p.user_id)}
    if token_id not in mine:
        raise HTTPException(404, "No such token.")
    tokens.revoke(get_db(request), _actor(p), token_id)
