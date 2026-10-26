from pathlib import Path
from typing import Annotated, Any

from cryptography import x509
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from cave import tls
from cave.access import netconfig
from cave.access.model import Principal
from cave.api.admin import _actor, _require
from cave.api.deps import current_principal, get_db
from cave.state import EventBus

router = APIRouter(prefix="/api/v1/system")
Caller = Annotated[Principal, Depends(current_principal)]


class Networks(BaseModel):
    local_ranges: list[str]
    trusted_proxies: list[str]


def _out(cfg: netconfig.NetConfig) -> dict[str, list[str]]:
    return {"local_ranges": list(cfg.local_ranges), "trusted_proxies": list(cfg.trusted_proxies)}


@router.get("/networks")
def get_networks(request: Request, p: Caller) -> dict[str, list[str]]:
    _require(request, p, "section:system")
    return _out(netconfig.load(get_db(request)))


@router.put("/networks")
def put_networks(body: Networks, request: Request, p: Caller) -> dict[str, list[str]]:
    _require(request, p, "section:system")
    try:
        cfg = netconfig.save(get_db(request), _actor(p), body.local_ranges, body.trusted_proxies)
    except netconfig.InvalidRange as e:
        raise HTTPException(422, str(e)) from e
    bus: EventBus = request.app.state.bus
    bus.publish({"type": "access_changed"})
    return _out(cfg)


@router.get("/certificate")
def get_certificate(request: Request, p: Caller) -> dict[str, Any]:
    _require(request, p, "section:system")
    cert: Path | None = getattr(request.app.state, "cert_path", None)
    if cert is None or not cert.exists():
        raise HTTPException(404, "CAVE isn't serving a certificate it can read.")
    c = x509.load_pem_x509_certificate(cert.read_bytes())
    return {
        "fingerprint": tls.fingerprint(cert),
        "not_after": tls.not_after(cert).isoformat(),
        "self_signed": c.issuer == c.subject,
    }
