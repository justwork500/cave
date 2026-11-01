import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from cave import audit
from cave.api.deps import PENDING_COOKIE, SESSION_COOKIE, get_db, now
from cave.auth import sessions
from cave.auth.users import (
    FAILED,
    LoginError,
    User,
    check_password,
    get_user,
    is_active,
    mfa_required,
    record_attempt,
    verify_second_factor,
)
from cave.state import EventBus

router = APIRouter(prefix="/api/v1")
PENDING_TTL = timedelta(minutes=5)
MAX_MFA_FAILURES = 5


@dataclass
class PendingMfa:
    user_id: str
    username: str
    expires: datetime
    failures: int = 0


class LoginBody(BaseModel):
    username: str
    password: str


class MfaBody(BaseModel):
    code: str


def _cookie(response: Response, name: str, value: str, max_age: int | None = None) -> None:
    response.set_cookie(name, value, max_age=max_age, secure=True, httponly=True, samesite="strict", path="/")


def _start_session(request: Request, response: Response, user: User) -> None:
    _cookie(response, SESSION_COOKIE, sessions.create(get_db(request), user.id, now()))
    audit.record(get_db(request), f"user:{user.id}", "auth.sign_in", f"user:{user.id}")


@router.post("/auth/login")
def login(body: LoginBody, request: Request, response: Response) -> dict[str, bool]:
    ip = request.client.host if request.client else ""
    try:
        user = check_password(get_db(request), body.username, body.password, ip, now())
    except LoginError as e:
        raise HTTPException(401, e.message) from e
    if mfa_required(user):
        # shortcut: pending MFA logins live in memory and are lost on restart; users just sign in again
        pending_id = secrets.token_urlsafe(32)
        request.app.state.pending_mfa[pending_id] = PendingMfa(user.id, user.username, now() + PENDING_TTL)
        _cookie(response, PENDING_COOKIE, pending_id, int(PENDING_TTL.total_seconds()))
        return {"mfa_required": True, "mfa_setup": True} if not user.has_totp else {"mfa_required": True}
    _start_session(request, response, user)
    return {"mfa_required": False}


@router.post("/auth/mfa")
def mfa(body: MfaBody, request: Request, response: Response) -> dict[str, bool]:
    pending: dict[str, PendingMfa] = request.app.state.pending_mfa
    pending_id = request.cookies.get(PENDING_COOKIE, "")
    entry = pending.get(pending_id)
    if entry is None or entry.expires < now():
        pending.pop(pending_id, None)
        raise HTTPException(401, "Sign in again.")
    db = get_db(request)
    if not verify_second_factor(db, entry.user_id, body.code):
        # each wrong code counts toward the password lockout, and a few of them end this sign-in
        record_attempt(db, entry.username, request.client.host if request.client else "", now(), FAILED)
        entry.failures += 1
        if entry.failures >= MAX_MFA_FAILURES:
            pending.pop(pending_id, None)
        raise HTTPException(401, "That code didn't work. Try the current code from your authenticator app.")
    pending.pop(pending_id)
    user = get_user(db, entry.user_id)
    if user is None or not is_active(user, now()):
        raise HTTPException(401, "Sign in again.")
    response.delete_cookie(PENDING_COOKIE, path="/")
    _start_session(request, response, user)
    return {"ok": True}


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response) -> None:
    session_id = request.cookies.get(SESSION_COOKIE)
    if session_id:
        sessions.end(get_db(request), session_id)
        bus: EventBus = request.app.state.bus
        bus.publish({"type": "session_ended", "session_id": session_id})
    response.delete_cookie(SESSION_COOKIE, path="/")

