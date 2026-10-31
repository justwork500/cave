from cave import audit
from tests.conftest import lan_client, sign_in


def as_admin(app, users):
    return sign_in(lan_client(app), "admin", "pw-admin-1234", users.admin_totp)


def test_area_crud_and_audit(app, users):
    c = as_admin(app, users)
    r = c.post("/api/v1/areas", json={"name": "Garage", "floor": "Ground"})
    assert r.status_code == 201 and r.json() == {"id": "garage", "name": "Garage", "floor": "Ground"}
    assert c.post("/api/v1/areas", json={"name": "garage!"}).json()["id"] == "garage_2"
    assert c.patch("/api/v1/areas/garage", json={"name": "Workshop"}).json()["name"] == "Workshop"
    assert [a["name"] for a in c.get("/api/v1/areas").json()] == ["garage!", "Workshop"]
    assert c.delete("/api/v1/areas/garage_2").status_code == 204
    actions = [e["action"] for e in audit.list_entries(app.state.db)]
    assert {"area.create", "area.update", "area.delete"} <= set(actions)


def test_rename_and_assign_room_shows_everywhere(app, users, garage):
    c = as_admin(app, users)
    c.post("/api/v1/areas", json={"name": "Garage"})
    r = c.patch("/api/v1/entities/cover.garage_door", json={"name": "Big door", "area_id": "garage"})
    assert r.status_code == 200
    states = {s["entity_id"]: s for s in c.get("/api/v1/states").json()}
    assert states["cover.garage_door"]["name"] == "Big door" and states["cover.garage_door"]["area_id"] == "garage"
    sam = sign_in(lan_client(app), "sam", "pw-sam-1234")
    stub = sam.get("/api/v1/states/cover.garage_door").json()
    assert stub == {"entity_id": "cover.garage_door", "name": "Big door", "area_id": "garage", "restricted": True}
    entry = next(e for e in audit.list_entries(app.state.db) if e["action"] == "entity.update")
    assert entry["new"] == {"name": "Big door", "area_id": "garage"}


def test_rename_needs_control(app, users, garage):
    op = sign_in(lan_client(app), "op", "pw-op-1234", users.op_totp)  # has Devices, can't control the garage
    assert op.patch("/api/v1/entities/cover.garage_door", json={"name": "x"}).status_code == 403


def test_unknown_area_refused(app, users, garage):
    c = as_admin(app, users)
    assert c.patch("/api/v1/entities/light.kids_room", json={"area_id": "nowhere"}).status_code == 422


def test_household_cannot_create_areas(app, users):
    sam = sign_in(lan_client(app), "sam", "pw-sam-1234")
    assert sam.post("/api/v1/areas", json={"name": "Den"}).status_code == 403
    assert sam.get("/api/v1/areas").status_code == 200


def test_deleting_area_clears_entity_area(app, users, garage):
    c = as_admin(app, users)
    c.post("/api/v1/areas", json={"name": "Kids"})
    c.patch("/api/v1/entities/light.kids_room", json={"area_id": "kids"})
    c.delete("/api/v1/areas/kids")
    assert c.get("/api/v1/states/light.kids_room").json()["area_id"] == "kids"  # back to the device's own room
