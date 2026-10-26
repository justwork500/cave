import asyncio
import contextlib
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from cave.access.evaluate import can_control
from cave.access.model import Principal
from cave.api.deps import client_ip, get_db, get_settings, now, principal_for_user, user_from_session
from cave.api.entities import DENIED
from cave.auth.users import get_user
from cave.state import Event, StateMachine

router = APIRouter(prefix="/api/v1")
CLOSE_UNAUTHORIZED = 4401


class _Socket:
    """One client connection: who it is, what it may see, and its subscription."""

    def __init__(self, ws: WebSocket, principal: Principal) -> None:
        self.ws = ws
        self.p = principal
        self.ip = client_ip(ws)
        self.local_ranges = get_settings(ws).local_ranges
        self.subscribed = False
        self._can: dict[str, bool] = {}

    def can(self, entity_id: str) -> bool:
        if entity_id not in self._can:
            self._can[entity_id] = can_control(get_db(self.ws), self.p, entity_id, self.ip, self.local_ranges)
        return self._can[entity_id]

    def refresh(self) -> bool:
        """Re-read the principal after an access change. False if it may no longer connect."""
        self._can.clear()
        user = get_user(get_db(self.ws), self.p.id) if self.p.user_id else None
        if user is None:
            return False
        self.p = principal_for_user(get_db(self.ws), user, now())
        return self.p.active

    async def on_event(self, event: Event) -> bool:
        """Handle one bus event. False means close the socket."""
        if event["type"] == "principal_disabled":
            return event.get("user_id") != self.p.user_id
        if event["type"] == "access_changed":
            return self.refresh()
        if event["type"] == "state_changed" and self.subscribed and self.can(event["entity_id"]):
            await self.ws.send_json({"type": "event", "event": event})
        return True

    async def on_message(self, msg: dict[str, Any], q: "asyncio.Queue[Event]") -> bool:
        msg_id, kind = msg.get("id"), msg.get("type")
        if kind == "subscribe":
            self.subscribed = "state_changed" in msg.get("events", [])
            await self.ws.send_json({"id": msg_id, "type": "result", "success": True})
        elif kind == "ping":
            # drain what is already queued first, so the pong marks a point in the event stream
            while not q.empty():
                if not await self.on_event(q.get_nowait()):
                    return False
            await self.ws.send_json({"id": msg_id, "type": "pong"})
        elif kind == "command":
            await self.ws.send_json({"id": msg_id, "type": "result", **await self._command(msg)})
        else:
            await self.ws.send_json({"id": msg_id, "type": "result", "success": False, "error": "Unknown message."})
        return True

    async def _command(self, msg: dict[str, Any]) -> dict[str, Any]:
        entity_id = str(msg.get("entity_id", ""))
        states: StateMachine = self.ws.app.state.states
        if not can_control(get_db(self.ws), self.p, entity_id, self.ip, self.local_ranges):
            return {"success": False, "error": DENIED}
        if states.entity(entity_id) is None:
            return {"success": False, "error": "No such device control."}
        try:
            await states.command(entity_id, str(msg.get("command", "")), dict(msg.get("args") or {}))
        except KeyError:
            return {"success": False, "error": "This device can't take commands right now."}
        return {"success": True}


@router.websocket("/ws")
async def websocket(ws: WebSocket) -> None:
    await ws.accept()
    user = user_from_session(ws)
    if user is None:
        await ws.close(CLOSE_UNAUTHORIZED)
        return
    sock = _Socket(ws, principal_for_user(get_db(ws), user, now()))
    bus = ws.app.state.bus
    q = bus.subscribe()
    recv = asyncio.ensure_future(ws.receive_json())
    get = asyncio.ensure_future(q.get())
    try:
        while True:
            done, _ = await asyncio.wait({recv, get}, return_when=asyncio.FIRST_COMPLETED)
            if get in done:
                if not await sock.on_event(get.result()):
                    await ws.close(CLOSE_UNAUTHORIZED)
                    return
                get = asyncio.ensure_future(q.get())
            if recv in done:
                try:
                    msg = recv.result()
                except WebSocketDisconnect:
                    return
                if not await sock.on_message(msg, q):
                    await ws.close(CLOSE_UNAUTHORIZED)
                    return
                recv = asyncio.ensure_future(ws.receive_json())
    finally:
        for f in (recv, get):
            f.cancel()
            with contextlib.suppress(asyncio.CancelledError, WebSocketDisconnect, RuntimeError):
                await f
        bus.unsubscribe(q)
