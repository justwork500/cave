from tests.conftest import sign_in

STUB = {"entity_id": "cover.garage_door", "name": "Garage door", "area_id": "garage", "restricted": True}


def by_id(rows):
    return {r["entity_id"]: r for r in rows}


def test_restricted_entity_is_stub(client, users, garage):
    sign_in(client, "sam", "pw-sam-1234")
    assert by_id(client.get("/api/v1/states").json())["cover.garage_door"] == STUB
    assert client.get("/api/v1/states/cover.garage_door").json() == STUB


def test_controllable_entity_is_full(client, users, garage):
    sign_in(client, "sam", "pw-sam-1234")
    row = by_id(client.get("/api/v1/states").json())["light.kids_room"]
    assert row["state"] == "off" and row["capability"] == "light" and "restricted" not in row


def test_admin_sees_everything_full(client, users, garage):
    sign_in(client, "admin", "pw-admin-1234", users.admin_totp)
    assert by_id(client.get("/api/v1/states").json())["cover.garage_door"]["state"] == "closed"


def test_unknown_entity_404(client, users, garage):
    sign_in(client, "sam", "pw-sam-1234")
    assert client.get("/api/v1/states/light.nope").status_code == 404


def test_states_require_sign_in(client, garage):
    assert client.get("/api/v1/states").status_code == 401
