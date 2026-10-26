from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from starlette.requests import HTTPConnection

from cave.access.model import Principal
from cave.access.network import IPAddress, resolve_client_ip
from cave.auth import sessions
from cave.auth.users import User, get_user, is_active
from cave.db import Database
from cave.settings import Settings

SESSION_COOKIE = "cave_session"
PENDING_COOKIE = "cave_pending"


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


def current_user(request: HTTPConnection) -> User:
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


def current_principal(request: HTTPConnection) -> Principal:
    return principal_for_user(get_db(request), current_user(request), now())


def client_ip(request: HTTPConnection) -> IPAddress:
    peer = request.client.host if request.client else ""
    return resolve_client_ip(peer, request.headers.get("x-forwarded-for"), get_settings(request).trusted_proxies)
