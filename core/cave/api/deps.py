"""Request dependencies: the database, settings, the caller (user, token or screen) and the client address."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from starlette.requests import HTTPConnection

from cave.access.model import Principal
from cave.access.netconfig import NetConfig
from cave.access.netconfig import load as load_netconfig
from cave.access.network import IPAddress, resolve_client_ip
from cave.auth import screens, sessions, tokens
from cave.auth.screens import Screen
from cave.auth.users import User, get_user, is_active
from cave.db import Database
from cave.settings import Settings

SESSION_COOKIE = "cave_session"
PENDING_COOKIE = "cave_pending"
SCREEN_COOKIE = "cave_screen"


def get_db(request: HTTPConnection) -> Database:
    db: Database = request.app.state.db
    return db


def get_settings(request: HTTPConnection) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def now() -> datetime:
    return datetime.now(UTC)


def user_from_session(request: HTTPConnection) -> User | None:
    session_id = request.cookies.get(SESSION_COOKIE)
    if not session_id:
        return None
    db = get_db(request)
    idle = timedelta(hours=get_settings(request).session_idle_hours)
    user_id = sessions.lookup(db, session_id, now(), idle)
    user = get_user(db, user_id) if user_id else None
    return user if user and is_active(user, now()) else None


def _bearer(request: HTTPConnection) -> tuple[str, User] | None:
    """(token_id, owner) for a live API token whose owner is active."""
    scheme, _, raw = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not raw:
        return None
    found = tokens.lookup(get_db(request), raw.strip())
    owner = get_user(get_db(request), found[1]) if found else None
    return (found[0], owner) if found and owner and is_active(owner, now()) else None


def current_user(request: HTTPConnection) -> User:
    if request.headers.get("authorization"):
        token = _bearer(request)
        if token is None:
            raise HTTPException(401, "That API token isn't valid.")
        return token[1]
    user = user_from_session(request)
    if user is None:
        raise HTTPException(401, "Sign in to continue.")
    return user


def principal_for_user(db: Database, user: User, at: datetime) -> Principal:
    groups = db.execute("SELECT group_id FROM group_members WHERE user_id=?", (user.id,)).fetchall()
    return Principal(
        kind="user",
        id=user.id,
        user_id=user.id,
        role=user.role,
        group_ids=frozenset(r["group_id"] for r in groups),
        active=is_active(user, at),
    )


def screen_principal(screen: Screen) -> Principal:
    return Principal(
        kind="screen",
        id=screen.id,
        user_id=None,
        role=None,
        group_ids=frozenset(),
        active=screen.status == "approved",
    )


def screen_from_cookie(request: HTTPConnection) -> Screen | None:
    session_id = request.cookies.get(SCREEN_COOKIE)
    return screens.screen_from_session(get_db(request), session_id, now()) if session_id else None


def current_principal(request: HTTPConnection) -> Principal:
    """Bearer token, then a person's session, then a screen's session."""
    if request.headers.get("authorization"):
        token = _bearer(request)
        if token is None:
            raise HTTPException(401, "That API token isn't valid.")
        return replace(principal_for_user(get_db(request), token[1], now()), kind="token", id=token[0])
    user = user_from_session(request)
    if user is not None:
        return principal_for_user(get_db(request), user, now())
    screen = screen_from_cookie(request)
    if screen is not None:
        return screen_principal(screen)
    raise HTTPException(401, "Sign in to continue.")


def net(request: HTTPConnection) -> NetConfig:
    """Network settings for this request, read once and cached on it."""
    cached: NetConfig | None = request.scope.get("cave.net")
    if cached is None:
        cached = load_netconfig(get_db(request))
        request.scope["cave.net"] = cached
    return cached


def client_ip(request: HTTPConnection) -> IPAddress:
    peer = request.client.host if request.client else ""
    forwarded = ",".join(request.headers.getlist("x-forwarded-for")) or None
    return resolve_client_ip(peer, forwarded, net(request).trusted_proxies)
