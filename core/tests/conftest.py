from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pyotp
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cave.api.app import create_app
from cave.auth.users import User, create_user, setup_totp
from cave.db import Database
from cave.settings import Settings

T0 = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    d = Database.open(tmp_path / "t.db")
    yield d
    d.close()


@dataclass
class Users:
    admin: User
    admin_totp: pyotp.TOTP
    sam: User
    op: User
    op_totp: pyotp.TOTP
    aud: User


@pytest.fixture
def app(tmp_path: Path) -> Iterator[FastAPI]:
    a = create_app(Settings(db_path=tmp_path / "app.db", config_dir=tmp_path, local_ranges=["192.168.1.0/24"]))
    yield a
    a.state.db.close()


@pytest.fixture
def users(app: FastAPI) -> Users:
    db = app.state.db
    admin = create_user(db, "system", "admin", "pw-admin-1234", "admin")
    op = create_user(db, "system", "op", "pw-op-1234", "operator")
    admin_uri, _ = setup_totp(db, admin.id)
    op_uri, _ = setup_totp(db, op.id)
    return Users(
        admin=admin,
        admin_totp=pyotp.parse_uri(admin_uri),
        sam=create_user(db, "system", "sam", "pw-sam-1234", "household"),
        op=op,
        op_totp=pyotp.parse_uri(op_uri),
        aud=create_user(db, "system", "aud", "pw-aud-1234", "auditor"),
    )


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app, base_url="https://testserver")


def sign_in(client: TestClient, username: str, password: str, totp: pyotp.TOTP | None = None) -> TestClient:
    r = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    if r.json()["mfa_required"]:
        assert totp is not None
        assert client.post("/api/v1/auth/mfa", json={"code": totp.now()}).status_code == 200
    return client
