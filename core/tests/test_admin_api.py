from tests.conftest import lan_client, sign_in


def as_admin(client, users):
    return sign_in(client, "admin", "pw-admin-1234", users.admin_totp)


def test_builtins_seeded_on_startup(app):
    assert app.state.db.execute("SELECT count(*) FROM items WHERE builtin=1").fetchone()[0] == 12


def test_last_admin_cannot_be_disabled_or_demoted(client, users):
    as_admin(client, users)
    url = f"/api/v1/users/{users.admin.id}"
    r = client.patch(url, json={"enabled": False})
    assert r.status_code == 409 and r.json() == {"detail": "CAVE needs at least one enabled Admin."}
    assert client.patch(url, json={"role": "household"}).status_code == 409
    r = client.post("/api/v1/users", json={"username": "admin2", "password": "pw-admin2-1234", "role": "admin"})
    assert r.status_code == 201
    assert client.patch(url, json={"role": "operator"}).status_code == 200


def test_operator_cannot_manage_users(client, users):
    sign_in(client, "op", "pw-op-1234", users.op_totp)
    assert client.get("/api/v1/users").status_code == 403
    assert client.patch(f"/api/v1/users/{users.sam.id}", json={"role": "admin"}).status_code == 403


def test_create_user_rejects_short_password(client, users):
    as_admin(client, users)
    r = client.post("/api/v1/users", json={"username": "kid", "password": "short", "role": "guest"})
    assert r.status_code == 422


def test_item_patch_is_audited_with_old_and_new(client, users):
    as_admin(client, users)
    assert client.patch("/api/v1/items/dashboard:home", json={"visibility": "show"}).status_code == 200
    entry = client.get("/api/v1/audit").json()[0]
    assert entry["action"] == "item.update" and entry["target"] == "item:dashboard:home"
    assert entry["old"]["visibility"] == "restrict" and entry["new"]["visibility"] == "show"
    assert entry["actor"] == f"user:{users.admin.id}"


def test_item_patch_rejects_bad_value(client, users):
    as_admin(client, users)
    assert client.patch("/api/v1/items/dashboard:home", json={"visibility": "everyone"}).status_code == 422


def test_assignment_change_takes_effect_immediately(app, client, users, garage):
    sam = sign_in(lan_client(app), "sam", "pw-sam-1234")
    assert sam.post("/api/v1/entities/cover.garage_door/commands/open", json={}).status_code == 403
    as_admin(client, users)
    r = client.put("/api/v1/items/dashboard:garage/assignments", json=[{"kind": "user", "id": users.sam.id}])
    assert r.status_code == 200
    assert client.get("/api/v1/items/dashboard:garage/assignments").json() == [{"kind": "user", "id": users.sam.id}]
    assert sam.post("/api/v1/entities/cover.garage_door/commands/open", json={}).status_code == 202


def test_get_items_respects_others_see(client, users, garage):
    sign_in(client, "sam", "pw-sam-1234")
    items = {i["id"]: i for i in client.get("/api/v1/items").json()}
    assert items["dashboard:garage"]["allowed"] is False  # Restrict, others see it locked
    assert items["dashboard:kids"]["allowed"] is True
    assert items["dashboard:home"]["allowed"] is True
    assert "section:users" not in items  # built-in: others see nothing


def test_auditor_reads_audit_but_cannot_patch_items(client, users):
    sign_in(client, "aud", "pw-aud-1234")
    assert client.get("/api/v1/audit").status_code == 200
    assert client.patch("/api/v1/items/dashboard:home", json={"visibility": "show"}).status_code == 403


def test_disabling_user_ends_sessions(app, client, users):
    sam = sign_in(lan_client(app), "sam", "pw-sam-1234")
    as_admin(client, users)
    assert client.patch(f"/api/v1/users/{users.sam.id}", json={"enabled": False}).status_code == 200
    assert sam.get("/api/v1/me").status_code == 401


def test_groups_and_membership(client, users):
    as_admin(client, users)
    g = client.post("/api/v1/groups", json={"name": "Lab crew"}).json()
    assert client.put(f"/api/v1/groups/{g['id']}/members", json=[users.sam.id]).status_code == 200
    groups = client.get("/api/v1/groups").json()
    assert groups == [{"id": g["id"], "name": "Lab crew", "members": [users.sam.id]}]
    assert client.delete(f"/api/v1/groups/{g['id']}").status_code == 204
    assert client.get("/api/v1/groups").json() == []


def test_group_membership_grants_access(app, client, users, garage):
    as_admin(client, users)
    g = client.post("/api/v1/groups", json={"name": "Garage users"}).json()
    client.put("/api/v1/items/dashboard:garage/assignments", json=[{"kind": "group", "id": g["id"]}])
    sam = sign_in(lan_client(app), "sam", "pw-sam-1234")
    assert sam.post("/api/v1/entities/cover.garage_door/commands/open", json={}).status_code == 403
    client.put(f"/api/v1/groups/{g['id']}/members", json=[users.sam.id])
    assert sam.post("/api/v1/entities/cover.garage_door/commands/open", json={}).status_code == 202
