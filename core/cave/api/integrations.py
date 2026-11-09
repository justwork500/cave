"""Adding devices to any registered integration: probe an address, pair, list, remove."""

from dataclasses import asdict
from ipaddress import ip_address
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from cave import audit
from cave.access.model import Principal
from cave.access.network import is_local
from cave.api.admin import _actor, _require
from cave.api.deps import current_principal, get_db, net
from cave.integrations.base import Device, Integrations, PairingError

router = APIRouter(prefix="/api/v1/integrations")
Caller = Annotated[Principal, Depends(current_principal)]
BAD_HOST = "Use the device's address on your home network, like 192.168.1.40."


class Probe(BaseModel):
    host: str = Field(max_length=64)


class AddDevice(Probe):
    secret: str | None = Field(default=None, max_length=256)


def _registry(request: Request, domain: str | None = None) -> Integrations:
    registry: Integrations = request.app.state.integrations
    if domain is not None and registry.get(domain) is None:
        raise HTTPException(404, "No such integration.")
    return registry


def _host(request: Request, host: str) -> str:
    try:
        ip = ip_address(host)
    except ValueError:
        raise HTTPException(422, BAD_HOST) from None
    if ip.is_loopback or not is_local(ip, net(request).local_ranges):
        raise HTTPException(422, BAD_HOST)
    return str(ip)


def _public(d: Device) -> dict[str, str]:
    return {"device_id": d.device_id, "host": d.host, "model": d.model, "name": d.name}


@router.get("")
def list_integrations(request: Request, p: Caller) -> list[dict[str, Any]]:
    _require(request, p, "section:devices")
    registry = _registry(request)
    return [{"domain": i.domain, "title": i.title, "pairing": i.pairing, "pairing_hint": i.pairing_hint,
             "devices": [_public(d) for d in registry.devices(i.domain)]} for i in registry.all()]


@router.post("/{domain}/probe")
async def probe(domain: str, body: Probe, request: Request, p: Caller) -> dict[str, Any]:
    _require(request, p, "section:devices")
    registry = _registry(request, domain)
    found = await registry.probe(domain, _host(request, body.host))
    if found is None:
        raise HTTPException(404, "Nothing CAVE recognizes answered at that address.")
    return asdict(found) | {"added": any(d.device_id == found.device_id for d in registry.devices(domain))}


@router.post("/{domain}/devices", status_code=201)
async def add_device(domain: str, body: AddDevice, request: Request, p: Caller) -> Any:
    _require(request, p, "section:devices")
    registry = _registry(request, domain)
    host = _host(request, body.host)
    before = {d.device_id: d for d in registry.devices(domain)}
    try:
        device, created = await registry.add(domain, host, body.secret, _actor(p))
    except PairingError as e:
        raise HTTPException(422, str(e)) from e
    target = f"integration:{domain}:{device.device_id}"
    if created:
        audit.record(get_db(request), _actor(p), "integration.add", target, None, _public(device))
        return _public(device)
    audit.record(get_db(request), _actor(p), "integration.update", target,
                 {"host": before[device.device_id].host}, {"host": device.host})
    return JSONResponse(_public(device), status_code=200)


@router.delete("/{domain}/devices/{device_id}", status_code=204)
def remove_device(domain: str, device_id: str, request: Request, p: Caller) -> None:
    _require(request, p, "section:devices")
    registry = _registry(request, domain)
    old = next((d for d in registry.devices(domain) if d.device_id == device_id), None)
    if old is None:
        raise HTTPException(404, "No such device.")
    registry.remove(domain, device_id, _actor(p))
    audit.record(get_db(request), _actor(p), "integration.remove", f"integration:{domain}:{device_id}",
                 _public(old), None)
