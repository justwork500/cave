"""What the console shows: dashboards rendered for one viewer, the Home summary, and the sign-in log.

Access is decided here, on the server. The browser only draws what comes back.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from cave.access.evaluate import can_control, can_run_script, evaluate
from cave.access.items import get_item
from cave.access.model import Principal
from cave.api.deps import client_ip, current_principal, get_db, net
from cave.api.entities import entity_view
from cave.config.models import (
    ButtonCard,
    Dashboard,
    EntitiesCard,
    GaugeCard,
    MarkdownCard,
    TileCard,
)
from cave.config.store import ConfigStore
from cave.integrations.mqtt.client import MqttService
from cave.state import State, StateMachine
from cave.templates import TemplateError, render

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1")
Caller = Annotated[Principal, Depends(current_principal)]
CARD_ERROR = "(this card couldn't be shown)"
SIGNIN_LABELS = {1: "signed in", 0: "wrong password or code", -1: "blocked (too many tries)"}


class _ViewerReader:
    """Templates on a dashboard read through the viewer's eyes: devices they can't control read as restricted."""

    def __init__(self, request: Request, p: Principal) -> None:
        self.request, self.p = request, p
        self.states: StateMachine = request.app.state.states

    def get(self, entity_id: str) -> State | None:
        if not can_control(get_db(self.request), self.p, entity_id, client_ip(self.request),
                           net(self.request).local_ranges):
            now = datetime.now(UTC)
            return State(entity_id, "restricted", {}, now, now)
        return self.states.get(entity_id)


def _allowed(request: Request, p: Principal, item_id: str) -> tuple[bool, bool]:
    item = get_item(get_db(request), item_id)
    if item is None:
        return False, False
    d = evaluate(get_db(request), p, item, client_ip(request), net(request).local_ranges)
    return d.allowed, d.listed


def _view(request: Request, p: Principal, entity_id: str) -> dict[str, Any]:
    states: StateMachine = request.app.state.states
    entity = states.entity(entity_id)
    if entity is None:
        return {"entity_id": entity_id, "name": entity_id, "area_id": None, "missing": True}
    return entity_view(get_db(request), p, entity, states.get(entity_id), client_ip(request),
                       net(request).local_ranges)


def _card(request: Request, p: Principal, card: Any) -> dict[str, Any] | None:
    out: dict[str, Any] = card.model_dump(mode="json", by_alias=True)
    if isinstance(card, TileCard | GaugeCard):
        out["entity"] = _view(request, p, card.entity)
        out["locked"] = bool(out["entity"].get("restricted"))
    elif isinstance(card, EntitiesCard):
        out["entities"] = [_view(request, p, e) for e in card.entities]
    elif isinstance(card, ButtonCard):
        if card.action:
            kind, ident = card.action.split(".", 1)
            allowed, listed = _allowed(request, p, f"{kind}:{ident}")
            if kind == "script" and get_item(get_db(request), f"script:{ident}") is not None:
                allowed = can_run_script(get_db(request), p, ident, client_ip(request), net(request).local_ranges)
                listed = listed or allowed  # the same rule as running it
            if not listed:
                return None
            out["allowed"] = allowed
        else:
            assert card.entity is not None
            out["allowed"] = can_control(get_db(request), p, card.entity, client_ip(request),
                                         net(request).local_ranges)
    elif isinstance(card, MarkdownCard):
        try:
            out["text"] = render(card.content, {}, _ViewerReader(request, p), datetime.now().astimezone())
        except TemplateError as e:
            log.warning("markdown card failed: %s", e)
            out["text"] = CARD_ERROR
    return out


@router.get("/dashboards/default")
def default_dashboard(request: Request, p: Caller) -> dict[str, str | None]:
    store: ConfigStore = request.app.state.config
    allowed = [(loaded.name, ident) for ident, loaded in store.list("dashboard")
               if _allowed(request, p, f"dashboard:{ident}")[0]]
    if any(ident == "home" for _, ident in allowed):
        return {"slug": "home"}
    return {"slug": min(allowed)[1] if allowed else None}


@router.get("/dashboards/{slug}/view")
def dashboard_view(slug: str, request: Request, p: Caller) -> dict[str, Any]:
    store: ConfigStore = request.app.state.config
    loaded = store.get("dashboard", slug)
    if loaded is None or not isinstance(loaded.doc, Dashboard):
        raise HTTPException(404, "No such dashboard.")
    if not _allowed(request, p, f"dashboard:{slug}")[0]:
        raise HTTPException(403, "You don't have access to this dashboard.")
    d = loaded.doc
    return {
        "slug": slug,
        "title": d.title,
        "icon": d.icon,
        "views": [
            {"id": v.id, "title": v.title, "sections": [
                {"title": s.title, "cards": [c for card in s.cards if (c := _card(request, p, card)) is not None]}
                for s in v.sections
            ]}
            for v in d.views
        ],
    }


@router.get("/summary")
def summary(request: Request, p: Caller) -> dict[str, Any]:
    db, ip, ranges = get_db(request), client_ip(request), net(request).local_ranges

    def has(*sections: str) -> bool:
        return any((item := get_item(db, s)) is not None and evaluate(db, p, item, ip, ranges).allowed
                   for s in sections)

    out: dict[str, Any] = {}
    if has("section:devices", "section:system"):
        service: MqttService | None = request.app.state.mqtt
        error: str | None = request.app.state.mqtt_error
        out["mqtt"] = ({"status": service.status, "entities": service.bridge.status()["entities"]} if service
                       else {"status": "failed" if error else "disabled", "entities": 0})
    if has("section:devices"):
        states: StateMachine = request.app.state.states
        out["unavailable"] = sum(
            1 for e in states.entities()
            if (s := states.get(e.entity_id)) is not None and s.value == "unavailable"
            and can_control(db, p, e.entity_id, ip, ranges)
        )
    if has("section:automations", "section:run_history"):
        since = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
        out["failures_24h"] = db.execute(
            "SELECT count(*) FROM automation_traces WHERE test=0 AND outcome='failed' AND finished_at>?", (since,)
        ).fetchone()[0]
    if has("section:users"):
        out["screens_pending"] = db.execute("SELECT count(*) FROM screens WHERE status='pending'").fetchone()[0]
    return out


@router.get("/signin-log")
def signin_log(request: Request, p: Caller, limit: int = 100) -> list[dict[str, Any]]:
    db = get_db(request)
    item = get_item(db, "section:signin_log")
    if item is None or not evaluate(db, p, item, client_ip(request), net(request).local_ranges).allowed:
        raise HTTPException(403, "You don't have access to this.")
    rows = db.execute("SELECT username, at, ok, ip FROM login_attempts ORDER BY rowid DESC LIMIT ?",
                      (min(max(limit, 1), 1000),)).fetchall()
    return [{"username": r["username"], "at": r["at"], "result": SIGNIN_LABELS.get(r["ok"], "unknown"),
             "ip": r["ip"]} for r in rows]
