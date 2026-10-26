from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request

from cave.auth import sessions
from cave.auth.users import User, get_user, is_active
from cave.db import Database
from cave.settings import Settings

SESSION_COOKIE = "cave_session"
PENDING_COOKIE = "cave_pending"


def get_db(request: Request) -> Database:
    db: Database = request.app.state.db
    return db


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def now() -> datetime:
    return datetime.now(UTC)


def user_from_session(request: Request) -> User | None:
    session_id = request.cookies.get(SESSION_COOKIE)
    if not session_id:
        return None
    db = get_db(request)
    idle = timedelta(hours=get_settings(request).session_idle_hours)
    user_id = sessions.lookup(db, session_id, now(), idle)
    user = get_user(db, user_id) if user_id else None
    return user if user and is_active(user, now()) else None


def current_user(request: Request) -> User:
    user = user_from_session(request)
    if user is None:
        raise HTTPException(401, "Sign in to continue.")
    return user
