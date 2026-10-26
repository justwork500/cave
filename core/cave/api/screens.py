from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from cave.access.model import Principal
from cave.api.admin import _actor, _require
from cave.api.deps import SCREEN_COOKIE, current_principal, get_db, now
from cave.auth import screens
from cave.auth.screens import EnrollError, Screen, ScreenStateError
from cave.state import EventBus

router = APIRouter(prefix="/api/v1")
Caller = Annotated[Principal, Depends(current_principal)]


def _out(s: Screen) -> dict[str, Any]:
    return {
        "id": s.id, "name": s.name, "status": s.status, "fingerprint": s.fingerprint,
        "created_at": s.created_at.isoformat(),
    }


def _publish(request: Request, event: dict[str, Any]) -> None:
    bus: EventBus = request.app.state.bus
    bus.publish(event)


class NewScreen(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class EnrollBody(BaseModel):
    code: str = Field(min_length=1, max_length=200)
    public_key: str = Field(min_length=1, max_length=2000)


@router.post("/screens", status_code=201)
def post_screen(body: NewScreen, request: Request, p: Caller) -> dict[str, Any]:
    _require(request, p, "section:users")
    at = now()
    screen, code = screens.create(get_db(request), _actor(p), body.name, at)
    host = request.headers.get("host", "localhost")
    # the code rides in the fragment, which browsers never send to the server (so it stays out of logs)
    return {
        "screen": _out(screen),
        "enroll_url": f"https://{host}/enroll#{code}",
        "expires_at": (at + screens.ENROLL_TTL).isoformat(),
    }


@router.get("/screens")
def get_screens(request: Request, p: Caller) -> list[dict[str, Any]]:
    _require(request, p, "section:users")
    return [_out(s) for s in screens.list_screens(get_db(request))]


@router.post("/screens/{screen_id}/approve")
def approve_screen(screen_id: str, request: Request, p: Caller) -> dict[str, Any]:
    _require(request, p, "section:users")
    if screens.get_screen(get_db(request), screen_id) is None:
        raise HTTPException(404, "No such screen.")
    try:
        s = screens.approve(get_db(request), _actor(p), screen_id, now())
    except ScreenStateError as e:
        raise HTTPException(409, str(e)) from e
    _publish(request, {"type": "access_changed"})
    return _out(s)


@router.post("/screens/{screen_id}/revoke")
def revoke_screen(screen_id: str, request: Request, p: Caller) -> dict[str, Any]:
    _require(request, p, "section:users")
    try:
        s = screens.revoke(get_db(request), _actor(p), screen_id)
    except KeyError as e:
        raise HTTPException(404, "No such screen.") from e
    _publish(request, {"type": "screen_revoked", "screen_id": screen_id})
    _publish(request, {"type": "access_changed"})
    return _out(s)


@router.post("/enroll")
def enroll(body: EnrollBody, request: Request) -> dict[str, Any]:
    try:
        s = screens.enroll(get_db(request), body.code, body.public_key, now())
    except EnrollError as e:
        raise HTTPException(400, e.message) from e
    return {"screen_id": s.id, "fingerprint": s.fingerprint, "status": s.status}


class ChallengeBody(BaseModel):
    screen_id: str = Field(min_length=1, max_length=64)


class VerifyBody(BaseModel):
    screen_id: str = Field(min_length=1, max_length=64)
    nonce: str = Field(min_length=1, max_length=200)
    signature: str = Field(max_length=200)


@router.post("/screen-auth/challenge")
def challenge(body: ChallengeBody, request: Request) -> dict[str, str]:
    try:
        return {"nonce": screens.issue_challenge(get_db(request), body.screen_id, now())}
    except EnrollError as e:
        raise HTTPException(401, screens.SIGNIN_FAILED) from e


@router.post("/screen-auth/verify", status_code=204)
def verify(body: VerifyBody, request: Request, response: Response) -> None:
    try:
        session_id = screens.verify_challenge(get_db(request), body.screen_id, body.nonce, body.signature, now())
    except EnrollError as e:
        raise HTTPException(401, e.message) from e
    response.set_cookie(
        SCREEN_COOKIE, session_id, max_age=int(screens.SESSION_MAX_AGE.total_seconds()),
        secure=True, httponly=True, samesite="strict", path="/",
    )
