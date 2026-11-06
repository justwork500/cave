"""Adding Kasa devices: sign in once with TP-Link, scan the local ranges, pick what to add."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from cave import audit
from cave.access.model import Principal
from cave.api.admin import _actor, _require
from cave.api.deps import current_principal, get_db, net
from cave.integrations.kasa.klap import KasaAuthError, KasaError
from cave.integrations.kasa.service import KasaService

router = APIRouter(prefix="/api/v1/kasa")
Caller = Annotated[Principal, Depends(current_principal)]


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=256)
    password: str = Field(min_length=1, max_length=256)


class AddDevice(BaseModel):
    mac: str = Field(min_length=12, max_length=12)


def _kasa(request: Request) -> KasaService:
    service: KasaService = request.app.state.kasa
    return service


@router.put("/login", status_code=204)
def set_login(body: Login, request: Request, p: Caller) -> None:
    _require(request, p, "section:devices")
    _kasa(request).set_login(body.username, body.password)
    audit.record(get_db(request), _actor(p), "kasa.login", "integration:kasa", None, {"signed_in": True})


@router.post("/scan")
async def scan(request: Request, p: Caller) -> dict[str, Any]:
    _require(request, p, "section:devices")
    return await _kasa(request).scan(net(request).local_ranges)


@router.post("/devices", status_code=201)
async def add_device(body: AddDevice, request: Request, p: Caller) -> dict[str, str]:
    _require(request, p, "section:devices")
    try:
        device = await _kasa(request).add(body.mac)
    except KeyError as e:
        raise HTTPException(404, "That device wasn't in the last scan. Scan again.") from e
    except KasaAuthError as e:
        raise HTTPException(409, "The device didn't accept this TP-Link sign-in.") from e
    except KasaError as e:
        raise HTTPException(409, "This device isn't responding.") from e
    audit.record(get_db(request), _actor(p), "kasa.add", f"kasa:{body.mac}", None, device)
    return device


@router.delete("/devices/{mac}", status_code=204)
def remove_device(mac: str, request: Request, p: Caller) -> None:
    _require(request, p, "section:devices")
    old = _kasa(request).remove(mac)
    if old is None:
        raise HTTPException(404, "No such device.")
    audit.record(get_db(request), _actor(p), "kasa.remove", f"kasa:{mac}", old, None)
