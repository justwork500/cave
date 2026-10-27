from pathlib import Path
from typing import Annotated, Any

from cryptography import x509
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from cave import tls
from cave.access import netconfig
from cave.access.evaluate import evaluate
from cave.access.items import get_item
from cave.access.model import Principal
from cave.api.admin import _actor, _require
from cave.api.deps import client_ip, current_principal, get_db, net
from cave.integrations.mqtt.client import MqttService
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


@router.get("/mqtt")
def get_mqtt(request: Request, p: Caller) -> dict[str, Any]:
    db = get_db(request)
    allowed = any(
        evaluate(db, p, item, client_ip(request), net(request).local_ranges).allowed
        for item in (get_item(db, "section:devices"), get_item(db, "section:system"))
        if item is not None
    )
    if not allowed:
        raise HTTPException(403, "You don't have access to this.")
    service: MqttService | None = request.app.state.mqtt
    error: str | None = request.app.state.mqtt_error
    if service is None:
        return {"status": "failed" if error else "disabled", "broker": None, "last_error": error,
                "entities": 0, "unsupported": []}
    b = service.cfg.broker
    return {"status": service.status, "broker": f"{b.host}:{b.port}", "last_error": service.last_error,
            **service.bridge.status()}
