from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from cave.access.evaluate import AccessDenied, evaluate
from cave.access.items import get_item
from cave.access.model import Principal
from cave.api.admin import _require
from cave.api.deps import client_ip, current_principal, get_db, net
from cave.config.yamlfile import ConfigError
from cave.scripts.header import FILE_NAME
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


def _out(s: LoadedScript) -> dict[str, Any]:
    return {"file": s.file, "name": s.header.name, "language": s.language,
            "header": s.header.model_dump(mode="json"), "text": s.text}


@router.get("")
def list_scripts(request: Request, p: Caller) -> list[dict[str, Any]]:
    _require(request, p, "section:scripts")
    db, ip, ranges = get_db(request), client_ip(request), net(request).local_ranges
    out = []
    for s in scripts(request).list():
        item = get_item(db, f"script:{s.file}")
        if item is not None:
            d = evaluate(db, p, item, ip, ranges)
            out.append({"file": s.file, "name": s.header.name, "language": s.language, "allowed": d.allowed})
    return out


@router.get("/{file}")
def get_script(file: str, request: Request, p: Caller) -> dict[str, Any]:
    _require(request, p, "section:scripts")
    loaded = scripts(request).get(_name(file))
    if loaded is None:
        raise HTTPException(404, "No such script.")
    return _out(loaded)


@router.put("/{file}")
def put_script(file: str, body: ScriptBody, request: Request, p: Caller) -> dict[str, Any]:
    _require(request, p, "section:scripts")
    try:
        return _out(scripts(request).save(_name(file), body.text, p))
    except ConfigError as e:
        raise HTTPException(422, str(e)) from e
    except AccessDenied as e:
        raise HTTPException(403, str(e)) from e


@router.delete("/{file}", status_code=204)
def delete_script(file: str, request: Request, p: Caller) -> None:
    _require(request, p, "section:scripts")
    try:
        scripts(request).delete(_name(file), p)
    except KeyError as e:
        raise HTTPException(404, "No such script.") from e
    except AccessDenied as e:
        raise HTTPException(403, str(e)) from e
