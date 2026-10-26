from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from cave.access.evaluate import can_control
from cave.access.model import Principal
from cave.api.deps import client_ip, current_principal, get_db, get_settings
from cave.state import StateMachine

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
    allowed = can_control(get_db(request), p, entity_id, client_ip(request), get_settings(request).local_ranges)
    if not allowed:
        raise HTTPException(403, DENIED)
    if states.entity(entity_id) is None:
        raise HTTPException(404, "No such device control.")
    try:
        await states.command(entity_id, command, args or {})
    except KeyError as e:
        raise HTTPException(409, "This device can't take commands right now.") from e
    return {"accepted": True}
