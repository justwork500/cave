"""Script API: list, read, save, delete and run scripts, and their run history."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from cave.access.evaluate import AccessDenied, can_run_script, evaluate
from cave.access.items import get_assignments, get_item
from cave.access.model import Principal
from cave.api.admin import _require
from cave.api.deps import client_ip, current_principal, get_db, net
from cave.config.yamlfile import ConfigError
from cave.scripts.header import FILE_NAME
from cave.scripts.service import ScriptService
from cave.scripts.store import LoadedScript, ScriptStore

router = APIRouter(prefix="/api/v1/scripts")
Caller = Annotated[Principal, Depends(current_principal)]


class ScriptBody(BaseModel):
    text: str = Field(max_length=256 * 1024)


def scripts(request: Request) -> ScriptStore:
    s: ScriptStore = request.app.state.scripts
    return s


def _name(file: str) -> str:
    if not FILE_NAME.fullmatch(file):  # before any file access
        raise HTTPException(404, "No such script.")
    return file


def _may_manage(request: Request, p: Principal, file: str) -> None:
    """The Scripts section covers every script, until an Admin restricts one by assigning it to someone."""
    db = get_db(request)
    item = get_item(db, f"script:{file}")
    if item is None or p.is_admin or not get_assignments(db, item.id):
        return
    if not evaluate(db, p, item, client_ip(request), net(request).local_ranges).allowed:
        raise HTTPException(403, "This script is restricted to others.")


def _out(s: LoadedScript) -> dict[str, Any]:
    return {"file": s.file, "name": s.header.name, "language": s.language,
            "header": s.header.model_dump(mode="json"), "text": s.text}


@router.get("")
def list_scripts(request: Request, p: Caller) -> list[dict[str, Any]]:
    _require(request, p, "section:scripts")
    db, ip, ranges = get_db(request), client_ip(request), net(request).local_ranges
    out = []
    for s in scripts(request).list():
        if get_item(db, f"script:{s.file}") is not None:
            allowed = can_run_script(db, p, s.file, ip, ranges)
            out.append({"file": s.file, "name": s.header.name, "language": s.language, "allowed": allowed})
    return out


@router.get("/{file}")
def get_script(file: str, request: Request, p: Caller) -> dict[str, Any]:
    _require(request, p, "section:scripts")
    _may_manage(request, p, _name(file))
    loaded = scripts(request).get(file)
    if loaded is None:
        raise HTTPException(404, "No such script.")
    return _out(loaded)


@router.put("/{file}")
def put_script(file: str, body: ScriptBody, request: Request, p: Caller) -> dict[str, Any]:
    _require(request, p, "section:scripts")
    _may_manage(request, p, _name(file))
    try:
        return _out(scripts(request).save(file, body.text, p))
    except ConfigError as e:
        raise HTTPException(422, str(e)) from e
    except AccessDenied as e:
        raise HTTPException(403, str(e)) from e


@router.delete("/{file}", status_code=204)
def delete_script(file: str, request: Request, p: Caller) -> None:
    _require(request, p, "section:scripts")
    _may_manage(request, p, _name(file))
    try:
        scripts(request).delete(file, p)
    except KeyError as e:
        raise HTTPException(404, "No such script.") from e
    except AccessDenied as e:
        raise HTTPException(403, str(e)) from e


# ---- running ----

class RunBody(BaseModel):
    params: dict[str, Any] = {}


@router.post("/{file}/run")
async def run_script(file: str, body: RunBody, request: Request, p: Caller) -> dict[str, Any]:
    _name(file)
    if not can_run_script(get_db(request), p, file, client_ip(request), net(request).local_ranges):
        raise HTTPException(403, "You don't have access to this.")
    service: ScriptService = request.app.state.script_service
    if service.runner is None:
        raise HTTPException(503, "The script runner isn't set up.")
    try:
        return {"result": await service.run(file, body.params, f"{p.kind}:{p.id}")}
    except ValueError as e:
        raise HTTPException(409, str(e)) from e


@router.get("/{file}/runs")
def script_runs(file: str, request: Request, p: Caller) -> list[dict[str, Any]]:
    _name(file)
    db, ip, ranges = get_db(request), client_ip(request), net(request).local_ranges
    sections = [get_item(db, "section:scripts"), get_item(db, "section:run_history")]
    if not any(s is not None and evaluate(db, p, s, ip, ranges).allowed for s in sections):
        raise HTTPException(403, "You don't have access to this.")
    _may_manage(request, p, file)
    service: ScriptService = request.app.state.script_service
    return service.runs(file)
