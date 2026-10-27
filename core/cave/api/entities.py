from collections.abc import Sequence
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from cave.access.evaluate import can_control
from cave.access.model import Principal
from cave.access.network import IPAddress
from cave.api.deps import client_ip, current_principal, get_db, net
from cave.db import Database
from cave.state import Entity, State, StateMachine

router = APIRouter(prefix="/api/v1")
DENIED = "You don't have access to this control."


def get_states(request: Request) -> StateMachine:
    states: StateMachine = request.app.state.states
    return states


@router.post("/entities/{entity_id}/commands/{command}", status_code=202)
async def run_command(
    entity_id: str,
    command: str,
    request: Request,
    p: Annotated[Principal, Depends(current_principal)],
    args: Annotated[dict[str, Any] | None, Body()] = None,
) -> dict[str, bool]:
    states = get_states(request)
    allowed = can_control(get_db(request), p, entity_id, client_ip(request), net(request).local_ranges)
    if not allowed:
        raise HTTPException(403, DENIED)
    if states.entity(entity_id) is None:
        raise HTTPException(404, "No such device control.")
    try:
        await states.command(entity_id, command, args or {})
    except KeyError as e:
        raise HTTPException(409, "This device can't take commands right now.") from e
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    return {"accepted": True}


def entity_view(
    db: Database, p: Principal, entity: Entity, state: State | None, ip: IPAddress, local_ranges: Sequence[str]
) -> dict[str, Any]:
    """Full view of what p controls; for everything else only that it exists and is restricted."""
    if not can_control(db, p, entity.entity_id, ip, local_ranges):
        return {"entity_id": entity.entity_id, "name": entity.name, "area_id": entity.area_id, "restricted": True}
    return {
        "entity_id": entity.entity_id,
        "name": entity.name,
        "area_id": entity.area_id,
        "capability": entity.capability,
        "state": state.value if state else None,
        "attributes": dict(state.attributes) if state else {},
        "last_changed": state.last_changed.isoformat() if state else None,
    }


@router.get("/states")
def list_states(request: Request, p: Annotated[Principal, Depends(current_principal)]) -> list[dict[str, Any]]:
    states, db, ip, ranges = get_states(request), get_db(request), client_ip(request), net(request).local_ranges
    return [entity_view(db, p, e, states.get(e.entity_id), ip, ranges) for e in states.entities()]


@router.get("/states/{entity_id}")
def get_state(entity_id: str, request: Request, p: Annotated[Principal, Depends(current_principal)]) -> dict[str, Any]:
    states = get_states(request)
    entity = states.entity(entity_id)
    if entity is None:
        raise HTTPException(404, "No such device control.")
    return entity_view(
        get_db(request), p, entity, states.get(entity_id), client_ip(request), net(request).local_ranges
    )
