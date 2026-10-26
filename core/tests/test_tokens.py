from cave.access.items import set_assignments
from tests.conftest import lan_client, sign_in


def give_sam_tokens(app):
    set_assignments(app.state.db, "test", "feature:api_tokens", [("role", "household")])


def make_token(app, users) -> str:
    give_sam_tokens(app)
    c = sign_in(lan_client(app), "sam", "pw-sam-1234")
    r = c.post("/api/v1/tokens", json={"name": "my script"})
    assert r.status_code == 201
    return r.json()["token"]


def bearer(app, token):
    c = lan_client(app)
    c.headers["Authorization"] = f"Bearer {token}"
    return c


def test_token_acts_as_owner(app, users, garage):
    c = bearer(app, make_token(app, users))
    assert c.post("/api/v1/entities/light.kids_room/commands/turn_on", json={}).status_code == 202
    assert c.post("/api/v1/entities/cover.garage_door/commands/open", json={}).status_code == 403


def test_other_users_token_cannot_command(app, users, garage):  # moved from Task 7
    c = bearer(app, make_token(app, users))
    assert c.post("/api/v1/entities/cover.garage_door/commands/open", json={}).status_code == 403
    assert c.get("/api/v1/me").json()["username"] == "sam"


def test_token_stored_hashed(app, users):
    token = make_token(app, users)
    assert token.startswith("cave_")
    dump = "\n".join(app.state.db._conn.iterdump())
    assert token not in dump


def test_revoked_token_401(app, users, garage):
    token = make_token(app, users)
    owner = sign_in(lan_client(app), "sam", "pw-sam-1234")
    [t] = owner.get("/api/v1/tokens").json()
    assert "token" not in t
    assert owner.delete(f"/api/v1/tokens/{t['id']}").status_code == 204
    assert bearer(app, token).get("/api/v1/me").status_code == 401


def test_disabled_owner_token_denied(app, users, garage):
    token = make_token(app, users)
    admin = sign_in(lan_client(app), "admin", "pw-admin-1234", users.admin_totp)
    admin.patch(f"/api/v1/users/{users.sam.id}", json={"enabled": False})
    assert bearer(app, token).post("/api/v1/entities/light.kids_room/commands/turn_on", json={}).status_code == 401


def test_create_requires_feature(app, users):
    c = sign_in(lan_client(app), "sam", "pw-sam-1234")
    assert c.post("/api/v1/tokens", json={"name": "x"}).status_code == 403


def test_garbage_bearer_401(app, users):
    assert bearer(app, "cave_nope").get("/api/v1/me").status_code == 401


def test_cannot_revoke_someone_elses_token(app, users):
    make_token(app, users)
    sam_tokens = sign_in(lan_client(app), "sam", "pw-sam-1234").get("/api/v1/tokens").json()
    give_sam_tokens(app)
    op = sign_in(lan_client(app), "op", "pw-op-1234", users.op_totp)
    assert op.get("/api/v1/tokens").json() == []
    assert op.delete(f"/api/v1/tokens/{sam_tokens[0]['id']}").status_code == 404


def test_admin_sees_all_tokens(app, users):
    make_token(app, users)
    admin = sign_in(lan_client(app), "admin", "pw-admin-1234", users.admin_totp)
    assert len(admin.get("/api/v1/tokens").json()) == 1
