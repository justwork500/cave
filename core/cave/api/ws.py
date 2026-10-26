import asyncio
import contextlib
import time
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from cave.access.evaluate import can_control
from cave.access.model import Principal
from cave.api.deps import SESSION_COOKIE, client_ip, get_db, get_settings, now, principal_for_user, user_from_session
from cave.api.entities import DENIED
from cave.auth.users import get_user
from cave.state import Event, StateMachine

router = APIRouter(prefix="/api/v1")
CLOSE_UNAUTHORIZED = 4401
CLOSE_FORBIDDEN_ORIGIN = 4403
CLOSE_RESYNC = 4408
RECHECK_SECONDS = 60.0  # how often an open socket re-validates its session (idle timeout, expiry)


class _Socket:
    """One client connection: who it is, what it may see, and its subscription."""

    def __init__(self, ws: WebSocket, principal: Principal, session_id: str) -> None:
        self.ws = ws
        self.p = principal
        self.session_id = session_id
        self.next_check = time.monotonic() + RECHECK_SECONDS
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

    def still_signed_in(self) -> bool:
        """Re-validate the session now and then, so idle timeouts and expiry end the live feed too."""
        if time.monotonic() < self.next_check:
            return True
        self.next_check = time.monotonic() + RECHECK_SECONDS
        user = user_from_session(self.ws)
        return user is not None and user.id == self.p.user_id

    async def on_event(self, event: Event) -> bool | int:
        """Handle one bus event. False (or a close code) means close the socket."""
        if event["type"] == "overflow":
            return CLOSE_RESYNC
        if event["type"] == "session_ended":
            return event.get("session_id") != self.session_id
        if not self.still_signed_in():
            return False
        if event["type"] == "principal_disabled":
            return event.get("user_id") != self.p.user_id
        if event["type"] == "access_changed":
            return self.refresh()
        if event["type"] == "state_changed" and self.subscribed and self.can(event["entity_id"]):
            await self.ws.send_json({"type": "event", "event": event})
        return True

    async def on_message(self, msg: dict[str, Any], q: "asyncio.Queue[Event]") -> bool | int:
        if not self.still_signed_in():
            return False
        msg_id, kind = msg.get("id"), msg.get("type")
        if kind == "subscribe":
            self.subscribed = "state_changed" in msg.get("events", [])
            await self.ws.send_json({"id": msg_id, "type": "result", "success": True})
        elif kind == "ping":
            # drain what is already queued first, so the pong marks a point in the event stream
            while not q.empty():
                result = await self.on_event(q.get_nowait())
                if result is not True:
                    return result
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


def _same_origin(ws: WebSocket) -> bool:
    """Browsers always send Origin; refuse pages from another host:port (cross-site WebSocket hijacking)."""
    origin = ws.headers.get("origin")
    return origin is None or urlsplit(origin).netloc.lower() == ws.headers.get("host", "").lower()


async def _close(ws: WebSocket, result: bool | int) -> None:
    await ws.close(CLOSE_UNAUTHORIZED if result is False else int(result))


@router.websocket("/ws")
async def websocket(ws: WebSocket) -> None:
    await ws.accept()
    if not _same_origin(ws):
        await ws.close(CLOSE_FORBIDDEN_ORIGIN)
        return
    user = user_from_session(ws)
    if user is None:
        await ws.close(CLOSE_UNAUTHORIZED)
        return
    sock = _Socket(ws, principal_for_user(get_db(ws), user, now()), ws.cookies.get(SESSION_COOKIE, ""))
    bus = ws.app.state.bus
    q = bus.subscribe()
    recv = asyncio.ensure_future(ws.receive_json())
    get = asyncio.ensure_future(q.get())
    try:
        while True:
            done, _ = await asyncio.wait({recv, get}, return_when=asyncio.FIRST_COMPLETED)
            if get in done:
                result = await sock.on_event(get.result())
                if result is not True:
                    await _close(ws, result)
                    return
                get = asyncio.ensure_future(q.get())
            if recv in done:
                try:
                    msg = recv.result()
                except WebSocketDisconnect:
                    return
                result = await sock.on_message(msg, q)
                if result is not True:
                    await _close(ws, result)
                    return
                recv = asyncio.ensure_future(ws.receive_json())
    finally:
        for f in (recv, get):
            f.cancel()
            with contextlib.suppress(asyncio.CancelledError, WebSocketDisconnect, RuntimeError):
                await f
        bus.unsubscribe(q)
