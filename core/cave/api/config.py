from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from cave.access.evaluate import AccessDenied, evaluate
from cave.access.items import get_item
from cave.access.model import Principal
from cave.api.admin import _require
from cave.api.deps import client_ip, current_principal, get_db, net
from cave.config.models import schema_files
from cave.config.store import ConfigStore, Kind, item_id
from cave.config.yamlfile import ConfigError
from cave.state import EventBus

router = APIRouter(prefix="/api/v1")
Caller = Annotated[Principal, Depends(current_principal)]
Plural = Literal["automations", "sequences", "dashboards"]
KINDS: dict[str, Kind] = {"automations": "automation", "sequences": "sequence", "dashboards": "dashboard"}
SECTIONS: dict[Kind, str] = {
    "automation": "section:automations", "sequence": "section:automations", "dashboard": "section:dashboards",
}


class YamlBody(BaseModel):
    yaml: str = Field(max_length=256 * 1024)


def store(request: Request) -> ConfigStore:
    s: ConfigStore = request.app.state.config
    return s


@router.post("/config/reload", status_code=204)
async def reload(request: Request, p: Caller) -> None:
    if not p.is_admin:
        raise HTTPException(403, "Only an Admin can reload config files.")
    store(request).load_all(f"{p.kind}:{p.id}")
    _changed(request)


@router.get("/config/errors")
def errors(request: Request, p: Caller) -> dict[str, str]:
    _require(request, p, "section:system")
    return dict(store(request).errors) | dict(request.app.state.scripts.errors)


@router.get("/schemas/{name}")
def schema(name: str, p: Caller) -> dict[str, Any]:
    files = schema_files()
    if name not in files:
        raise HTTPException(404, "No such schema.")
    return files[name]


@router.get("/{kinds}")
def list_docs(kinds: Plural, request: Request, p: Caller) -> list[dict[str, Any]]:
    db, ip, ranges = get_db(request), client_ip(request), net(request).local_ranges
    out = []
    for ident, loaded in store(request).list(KINDS[kinds]):
        item = get_item(db, item_id(KINDS[kinds], ident))
        if item is None:
            continue
        d = evaluate(db, p, item, ip, ranges)
        if d.listed:
            out.append({"id": ident, "name": item.name, "allowed": d.allowed})
    return out


@router.get("/{kinds}/{ident}")
def get_doc(kinds: Plural, ident: str, request: Request, p: Caller) -> dict[str, Any]:
    kind = KINDS[kinds]
    loaded = store(request).get(kind, ident)
    item = get_item(get_db(request), item_id(kind, ident))
    if loaded is None or item is None:
        raise HTTPException(404, "Not found.")
    ip, ranges = client_ip(request), net(request).local_ranges
    if not evaluate(get_db(request), p, item, ip, ranges).allowed:
        raise HTTPException(403, "You don't have access to this.")
    try:  # reading the YAML shows every device it names, so it needs the same rule as saving
        store(request).guard(p, loaded.refs, ip, ranges)
    except AccessDenied as e:
        raise HTTPException(403, str(e)) from e
    return {"id": ident, "name": item.name, "yaml": loaded.text}


@router.put("/{kinds}/{ident}")
async def put_doc(kinds: Plural, ident: str, body: YamlBody, request: Request, p: Caller) -> dict[str, Any]:
    kind = KINDS[kinds]
    _require(request, p, SECTIONS[kind])
    try:
        loaded = store(request).save(kind, ident, body.yaml, p, client_ip(request), net(request).local_ranges)
    except ConfigError as e:
        raise HTTPException(422, str(e)) from e
    except AccessDenied as e:
        raise HTTPException(403, str(e)) from e
    _changed(request)
    return {"id": ident, "name": loaded.name}


@router.delete("/{kinds}/{ident}", status_code=204)
async def delete_doc(kinds: Plural, ident: str, request: Request, p: Caller) -> None:
    kind = KINDS[kinds]
    _require(request, p, SECTIONS[kind])
    try:
        store(request).delete(kind, ident, p, client_ip(request), net(request).local_ranges)
    except KeyError as e:
        raise HTTPException(404, "Not found.") from e
    except AccessDenied as e:
        raise HTTPException(403, str(e)) from e
    _changed(request)


def _changed(request: Request) -> None:
    bus: EventBus = request.app.state.bus
    bus.publish({"type": "access_changed"})
    rearm = getattr(request.app.state, "rearm", None)
    if rearm is not None:
        rearm()


