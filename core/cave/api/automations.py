"""Automation API: notifications, Test Center runs, running actions by hand, and run traces."""

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
from cave.config.store import ConfigStore, item_id, parse
from cave.config.yamlfile import ConfigError
from cave.scripts.service import ScriptService

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
    db, ip, ranges = get_db(request), client_ip(request), net(request).local_ranges
    item = get_item(db, item_id(body.kind, body.id))
    if item is not None and not evaluate(db, p, item, ip, ranges).allowed:
        raise HTTPException(403, "You don't have access to this.")
    deep = store.deep_refs(doc)
    try:  # a trace shows what the run read, routines included, so the save rule applies all the way down
        store.guard(p, deep, ip, ranges)
    except AccessDenied as e:
        raise HTTPException(403, str(e)) from e
    service: ScriptService = request.app.state.script_service
    samples = {ref: s for ref in deep.scripts if (s := service.sample(ref.removeprefix("scripts/"))) is not None}
    trace = await what_if(
        doc, trigger=body.trigger, states=body.states, variables=dict(body.variables), start_at=body.start_at,
        script_samples=samples | body.script_samples, reader=request.app.state.states, sequences=store.sequence,
        now=datetime.now().astimezone(),
    )
    iid = item_id(body.kind, body.id)
    if body.yaml is None and item is not None:
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
    loaded = store.get(kind, ident)
    if body.variables and not p.is_admin and loaded is not None and store.deep_refs(loaded.doc).dynamic_template:
        # the routine reads devices by name from its inputs; choosing those names is an Admin's call
        raise HTTPException(403, "Only an Admin can pass values to this routine.")
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
    item = get_item(db, item_id(kind, ident))
    if item is None or not evaluate(db, p, item, ip, ranges).allowed:
        raise HTTPException(403, "You don't have access to this.")
    rows = list_traces(db, item_id(kind, ident), test)
    store: ConfigStore = request.app.state.config
    loaded = store.get(kind, ident)
    deep = store.deep_refs(loaded.doc) if loaded else None
    # step details carry rendered device values, so they need control of every device the run could read
    hidden = not p.is_admin and (deep is None or deep.dynamic_template or not all(
        can_control(db, p, e, ip, ranges) for e in deep.entities))
    if hidden:
        for row in rows:
            row["trace"]["variables"], row["trace"]["error"] = {}, None
            for step in row["trace"]["steps"]:
                step["detail"], step["data"] = "restricted", {}
    return rows
