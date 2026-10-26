import secrets
from datetime import timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from cave import audit
from cave.api.deps import PENDING_COOKIE, SESSION_COOKIE, current_user, get_db, now
from cave.auth import sessions
from cave.auth.users import LoginError, User, check_password, get_user, mfa_required, verify_second_factor

router = APIRouter(prefix="/api/v1")
PENDING_TTL = timedelta(minutes=5)


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
        request.app.state.pending_mfa[pending_id] = (user.id, now() + PENDING_TTL)
        _cookie(response, PENDING_COOKIE, pending_id, int(PENDING_TTL.total_seconds()))
        return {"mfa_required": True}
    _start_session(request, response, user)
    return {"mfa_required": False}


@router.post("/auth/mfa")
def mfa(body: MfaBody, request: Request, response: Response) -> dict[str, bool]:
    pending: dict[str, tuple[str, Any]] = request.app.state.pending_mfa
    entry = pending.get(request.cookies.get(PENDING_COOKIE, ""))
    if entry is None or entry[1] < now():
        raise HTTPException(401, "Sign in again.")
    user_id = entry[0]
    if not verify_second_factor(get_db(request), user_id, body.code):
        raise HTTPException(401, "That code didn't work. Try the current code from your authenticator app.")
    pending.pop(request.cookies[PENDING_COOKIE])
    user = get_user(get_db(request), user_id)
    assert user is not None
    response.delete_cookie(PENDING_COOKIE, path="/")
    _start_session(request, response, user)
    return {"ok": True}


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response) -> None:
    session_id = request.cookies.get(SESSION_COOKIE)
    if session_id:
        sessions.end(get_db(request), session_id)
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me")
def me(user: Annotated[User, Depends(current_user)]) -> dict[str, str]:
    return {"id": user.id, "username": user.username, "display_name": user.display_name, "role": user.role}
