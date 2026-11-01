"""First-run setup (the owner account), authenticator enrollment, and changing your own password."""

import hashlib
import hmac
import secrets
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from cave import audit
from cave.access.evaluate import evaluate
from cave.access.items import BUILTIN_SECTIONS, get_item
from cave.access.model import Principal
from cave.api.auth import PENDING_TTL, PendingMfa, _cookie
from cave.api.deps import (
    PENDING_COOKIE,
    SESSION_COOKIE,
    client_ip,
    current_principal,
    current_user,
    get_db,
    net,
    now,
)
from cave.auth import sessions
from cave.auth.passwords import hash_password
from cave.auth.screens import get_screen
from cave.auth.users import LoginError, User, check_password, get_user, setup_totp
from cave.db import Database

router = APIRouter(prefix="/api/v1")
MIN_PASSWORD = 12
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I to misread


def _hash(code: str) -> str:
    return hashlib.sha256(code.strip().upper().encode()).hexdigest()


def ensure_setup_code(db: Database) -> str | None:
    """While no one has set CAVE up, every start makes a fresh one-time code (the old one stops working).
    `cave serve` prints it: only someone who can see the server's console can claim CAVE."""
    if db.execute("SELECT count(*) FROM users").fetchone()[0]:
        return None
    code = "-".join("".join(secrets.choice(CODE_ALPHABET) for _ in range(4)) for _ in range(4))
    with db.transaction() as conn:
        conn.execute("DELETE FROM setup_code")
        conn.execute("INSERT INTO setup_code (code_hash) VALUES (?)", (_hash(code),))
    return code


class SetupBody(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=MIN_PASSWORD, max_length=1024)
    display_name: str = Field(default="", max_length=100)


@router.get("/setup")
def setup_needed(request: Request) -> dict[str, bool]:
    return {"needed": get_db(request).execute("SELECT count(*) FROM users").fetchone()[0] == 0}


@router.post("/setup")
def setup(body: SetupBody, request: Request, response: Response) -> dict[str, Any]:
    db = get_db(request)
    with db.transaction() as conn:  # one transaction: two people racing can't both become the owner
        if conn.execute("SELECT count(*) FROM users").fetchone()[0]:
            raise HTTPException(409, "CAVE is already set up. Sign in instead.")
        row = conn.execute("SELECT code_hash FROM setup_code").fetchone()
        if row is None or not hmac.compare_digest(row["code_hash"], _hash(body.code)):
            raise HTTPException(403, "That setup code isn't right.")
        conn.execute("DELETE FROM setup_code")
        conn.execute(
            "INSERT INTO users (id, username, display_name, role, password_hash, created_at) "
            "VALUES (?, ?, ?, 'admin', ?, ?)",
            (secrets.token_hex(16), body.username, body.display_name or body.username,
             hash_password(body.password), now().isoformat()),
        )
    user_id = db.execute("SELECT id FROM users WHERE username=?", (body.username,)).fetchone()["id"]
    audit.record(db, f"user:{user_id}", "setup.owner_created", f"user:{user_id}", None, {"username": body.username})
    uri, codes = setup_totp(db, user_id)
    _pending(request, response, user_id, body.username)
    return {"provisioning_uri": uri, "recovery_codes": codes}


def _pending(request: Request, response: Response, user_id: str, username: str) -> None:
    pending_id = secrets.token_urlsafe(32)
    request.app.state.pending_mfa[pending_id] = PendingMfa(user_id, username, now() + PENDING_TTL)
    _cookie(response, PENDING_COOKIE, pending_id, int(PENDING_TTL.total_seconds()))


@router.post("/auth/mfa/setup")
def mfa_setup(request: Request) -> dict[str, Any]:
    """A user who must use an authenticator but hasn't set one up yet, half-way through signing in."""
    pending: dict[str, PendingMfa] = request.app.state.pending_mfa
    entry = pending.get(request.cookies.get(PENDING_COOKIE, ""))
    if entry is None or entry.expires < now():
        raise HTTPException(401, "Sign in again.")
    user = get_user(get_db(request), entry.user_id)
    if user is None:
        raise HTTPException(401, "Sign in again.")
    if user.has_totp:
        raise HTTPException(409, "You already have an authenticator app set up.")
    uri, codes = setup_totp(get_db(request), user.id)
    return {"provisioning_uri": uri, "recovery_codes": codes}


@router.get("/me")
def me(request: Request, p: Annotated[Principal, Depends(current_principal)]) -> dict[str, Any]:
    db = get_db(request)
    if p.kind == "screen":
        screen = get_screen(db, p.id)
        return {"kind": "screen", "id": p.id, "username": None, "display_name": screen.name if screen else p.id,
                "role": None, "has_totp": False, "sections": []}
    user = get_user(db, p.user_id or "")
    assert user is not None
    ip, ranges = client_ip(request), net(request).local_ranges
    sections = [s for s in BUILTIN_SECTIONS if (item := get_item(db, s)) and evaluate(db, p, item, ip, ranges).allowed]
    return {"kind": p.kind, "id": user.id, "username": user.username, "display_name": user.display_name,
            "role": user.role, "has_totp": user.has_totp, "sections": sections}


class PasswordBody(BaseModel):
    current: str = Field(max_length=1024)
    new: str = Field(min_length=MIN_PASSWORD, max_length=1024)


@router.post("/me/password", status_code=204)
def change_password(body: PasswordBody, request: Request, user: Annotated[User, Depends(current_user)]) -> None:
    db = get_db(request)
    session_id = request.cookies.get(SESSION_COOKIE)
    if session_id is None:
        raise HTTPException(403, "Change your password from a signed-in browser, not with an API token.")
    try:  # the sign-in check, lockout included, so a stolen session can't guess the password freely
        check_password(db, user.username, body.current, request.client.host if request.client else "", now())
    except LoginError as e:
        if e.locked:
            raise HTTPException(429, e.message) from e
        raise HTTPException(403, "That's not your current password.") from e
    db.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(body.new), user.id))
    sessions.end_others(db, user.id, session_id)
    audit.record(db, f"user:{user.id}", "user.password_changed", f"user:{user.id}")

