"""Rooms (areas), and renaming a device or moving it to a room."""

import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from cave import audit
from cave.access.evaluate import can_control
from cave.access.model import Principal
from cave.api.admin import _actor, _require
from cave.api.deps import client_ip, current_principal, get_db, net
from cave.db import Database
from cave.state import EventBus, StateMachine

router = APIRouter(prefix="/api/v1")
Caller = Annotated[Principal, Depends(current_principal)]


class AreaBody(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    floor: str | None = Field(default=None, max_length=64)


class AreaPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    floor: str | None = Field(default=None, max_length=64)


class EntityPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    area_id: str | None = Field(default=None, max_length=80)


def _area(db: Database, area_id: str) -> dict[str, Any] | None:
    row = db.execute("SELECT id, name, floor FROM areas WHERE id=?", (area_id,)).fetchone()
    return dict(row) if row else None


def overrides(db: Database, entity_id: str) -> tuple[str | None, str | None]:
    """(name, area_id) an Admin gave this device, if any."""
    row = db.execute("SELECT name, area_id FROM entity_overrides WHERE entity_id=?", (entity_id,)).fetchone()
    return (row["name"], row["area_id"]) if row else (None, None)


@router.get("/areas")
def list_areas(request: Request, p: Caller) -> list[dict[str, Any]]:
    return [dict(r) for r in get_db(request).execute("SELECT id, name, floor FROM areas ORDER BY name").fetchall()]


@router.post("/areas", status_code=201)
def create_area(body: AreaBody, request: Request, p: Caller) -> dict[str, Any]:
    _require(request, p, "section:devices")
    db = get_db(request)
    base = re.sub(r"[^a-z0-9]+", "_", body.name.lower()).strip("_")[:60] or "room"
    ident, n = base, 2
    while _area(db, ident):
        ident, n = f"{base}_{n}", n + 1
    try:
        db.execute("INSERT INTO areas (id, name, floor) VALUES (?, ?, ?)", (ident, body.name, body.floor))
    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(409, "There's already a room with that name.") from e
        raise
    area = _area(db, ident)
    audit.record(db, _actor(p), "area.create", f"area:{ident}", None, area)
    assert area is not None
    return area


@router.patch("/areas/{area_id}")
def update_area(area_id: str, body: AreaPatch, request: Request, p: Caller) -> dict[str, Any]:
    _require(request, p, "section:devices")
    db = get_db(request)
    old = _area(db, area_id)
    if old is None:
        raise HTTPException(404, "No such room.")
    new = old | body.model_dump(exclude_unset=True)
    try:
        db.execute("UPDATE areas SET name=?, floor=? WHERE id=?", (new["name"], new["floor"], area_id))
    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(409, "There's already a room with that name.") from e
        raise
    audit.record(db, _actor(p), "area.update", f"area:{area_id}", old, new)
    return new


@router.delete("/areas/{area_id}", status_code=204)
def delete_area(area_id: str, request: Request, p: Caller) -> None:
    _require(request, p, "section:devices")
    db = get_db(request)
    old = _area(db, area_id)
    if old is None:
        raise HTTPException(404, "No such room.")
    db.execute("DELETE FROM areas WHERE id=?", (area_id,))
    audit.record(db, _actor(p), "area.delete", f"area:{area_id}", old, None)
    _changed(request)


@router.patch("/entities/{entity_id}")
def update_entity(entity_id: str, body: EntityPatch, request: Request, p: Caller) -> dict[str, Any]:
    _require(request, p, "section:devices")
    db = get_db(request)
    states: StateMachine = request.app.state.states
    if states.entity(entity_id) is None:
        raise HTTPException(404, "No such device control.")
    if not can_control(db, p, entity_id, client_ip(request), net(request).local_ranges):
        raise HTTPException(403, "You can only rename devices you can control.")
    if body.area_id is not None and _area(db, body.area_id) is None:
        raise HTTPException(422, "There's no room with that id.")
    old_name, old_area = overrides(db, entity_id)
    changes = body.model_dump(exclude_unset=True)
    name, area = changes.get("name", old_name), changes.get("area_id", old_area)
    db.execute(
        "INSERT INTO entity_overrides (entity_id, name, area_id) VALUES (?, ?, ?) "
        "ON CONFLICT(entity_id) DO UPDATE SET name=excluded.name, area_id=excluded.area_id",
        (entity_id, name, area),
    )
    audit.record(db, _actor(p), "entity.update", f"entity:{entity_id}",
                 {"name": old_name, "area_id": old_area}, {"name": name, "area_id": area})
    _changed(request)
    return {"entity_id": entity_id, "name": name, "area_id": area}


def _changed(request: Request) -> None:
    bus: EventBus = request.app.state.bus
    bus.publish({"type": "access_changed"})  # open sockets re-read names and rooms
