import dataclasses
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from cave import notifications
from cave.access.evaluate import AccessDenied, can_control, evaluate
from cave.access.items import get_item
from cave.access.model import Principal
from cave.api.admin import _require
from cave.api.deps import client_ip, current_principal, get_db, net
from cave.automation.manager import AutomationManager, finish_trace, list_traces, new_trace
from cave.automation.whatif import what_if
from cave.config.models import Automation, Sequence
from cave.config.refs import refs
from cave.config.store import ConfigStore, item_id, parse
from cave.config.yamlfile import ConfigError

router = APIRouter(prefix="/api/v1")
Caller = Annotated[Principal, Depends(current_principal)]


def _person(p: Principal) -> str:
    if p.user_id is None:
        raise HTTPException(403, "Screens don't have notifications.")
    return p.user_id


class ReadBody(BaseModel):
    ids: list[int] = Field(max_length=1000)


@router.get("/notifications")
def get_notifications(request: Request, p: Caller, unread: bool = False) -> list[dict[str, Any]]:
    return notifications.list_for(get_db(request), _person(p), unread)


@router.post("/notifications/read", status_code=204)
def read_notifications(body: ReadBody, request: Request, p: Caller) -> None:
    notifications.mark_read(get_db(request), _person(p), body.ids)


# ---- the Test Center ----

class TestRun(BaseModel):
    kind: Literal["automation", "sequence"]
    id: str = Field(min_length=1, max_length=64)
    yaml: str | None = Field(default=None, max_length=256 * 1024)
    trigger: dict[str, Any] | None = None
    states: dict[str, str | dict[str, Any]] = {}
    variables: dict[str, Any] = {}
    start_at: str | None = Field(default=None, max_length=500)
    script_samples: dict[str, dict[str, Any]] = {}


@router.post("/test-center/run")
async def test_center(body: TestRun, request: Request, p: Caller) -> dict[str, Any]:
    _require(request, p, "feature:test_center", "use")
    store: ConfigStore = request.app.state.config
    if body.yaml is not None:  # a draft: validated, never written
        try:
            doc = parse(body.kind, body.id, body.yaml)
        except ConfigError as e:
            raise HTTPException(422, str(e)) from e
    else:
        loaded = store.get(body.kind, body.id)
        if loaded is None:
            raise HTTPException(404, "Not found.")
        doc = loaded.doc
    assert isinstance(doc, Automation | Sequence)
    try:  # a trace shows real values for devices you didn't simulate, so the save rule applies
        store.guard(p, refs(doc), client_ip(request), net(request).local_ranges)
    except AccessDenied as e:
        raise HTTPException(403, str(e)) from e
    trace = await what_if(
        doc, trigger=body.trigger, states=body.states, variables=dict(body.variables), start_at=body.start_at,
        script_samples=body.script_samples, reader=request.app.state.states, sequences=store.sequence,
        now=datetime.now().astimezone(),
    )
    db = get_db(request)
    iid = item_id(body.kind, body.id)
    if body.yaml is None and get_item(db, iid) is not None:
        finish_trace(db, iid, new_trace(db, iid, test=True), trace)
    return {"trace": dataclasses.asdict(trace),
            "summary": {"devices_changed": 0, "messages_sent": 0, "scripts_run": 0}}


# ---- manual runs and traces ----

Runnable = Literal["automations", "sequences"]
RUN_KINDS: dict[str, Literal["automation", "sequence"]] = {"automations": "automation", "sequences": "sequence"}


class RunBody(BaseModel):
    variables: dict[str, Any] = {}


@router.post("/{kinds}/{ident}/run")
async def run_action(kinds: Runnable, ident: str, body: RunBody, request: Request, p: Caller) -> dict[str, int]:
    kind = RUN_KINDS[kinds]
    db = get_db(request)
    store: ConfigStore = request.app.state.config
    item = get_item(db, item_id(kind, ident))
    if item is None or store.get(kind, ident) is None:
        raise HTTPException(404, "Not found.")
    if not evaluate(db, p, item, client_ip(request), net(request).local_ranges).allowed:
        raise HTTPException(403, "You don't have access to this.")
    manager: AutomationManager | None = request.app.state.automations
    if manager is None:
        raise HTTPException(503, "Automations aren't running right now.")
    if kind == "automation":  # a button press: no triggers, no conditions
        trace_id = manager.fire(ident, {"type": "manual", "by": f"{p.kind}:{p.id}"}, check_conditions=False)
    else:
        trace_id = manager.run_sequence(ident, body.variables)
    if trace_id is None:
        raise HTTPException(409, "It's already running.")
    return {"trace_id": trace_id}


@router.get("/{kinds}/{ident}/traces")
def get_traces(kinds: Runnable, ident: str, request: Request, p: Caller, test: bool = False) -> list[dict[str, Any]]:
    db, ip, ranges = get_db(request), client_ip(request), net(request).local_ranges
    sections = [get_item(db, "section:run_history"), get_item(db, "section:automations")]
    if not any(s is not None and evaluate(db, p, s, ip, ranges).allowed for s in sections):
        raise HTTPException(403, "You don't have access to this.")
    kind = RUN_KINDS[kinds]
    rows = list_traces(db, item_id(kind, ident), test)
    loaded = request.app.state.config.get(kind, ident)
    # step details carry rendered device values, so they need control of every device the automation names
    hidden = not p.is_admin and (loaded is None or not all(
        can_control(db, p, e, ip, ranges) for e in loaded.refs.entities))
    if hidden:
        for row in rows:
            row["trace"]["variables"], row["trace"]["error"] = {}, None
            for step in row["trace"]["steps"]:
                step["detail"], step["data"] = "restricted", {}
    return rows
