import asyncio
from datetime import UTC, datetime

import pytest

from cave import notifications
from cave.automation.effects import LiveEffects
from cave.state import Entity, EventBus, StateMachine
from tests.conftest import lan_client, sign_in
from tests.test_ws import connect, ping


def saved_by(db, item_id, user_id):
    db.execute("INSERT INTO config_saves (item_id, user_id, saved_at) VALUES (?, ?, ?)",
               (item_id, user_id, datetime.now(UTC).isoformat()))


def test_recipients_default_to_last_saver_then_admins(app, users):
    db = app.state.db
    assert notifications.recipients(db, ["notify.cave"], "automation:x") == [users.admin.id]
    saved_by(db, "automation:x", users.op.id)
    assert notifications.recipients(db, ["notify.cave"], "automation:x") == [users.op.id]
    assert notifications.recipients(db, [], "automation:x") == [users.op.id]
    assert sorted(notifications.recipients(db, ["user:sam", "user:aud", "user:nobody"], "automation:x")) == sorted(
        [users.sam.id, users.aud.id])


def test_disabled_user_skipped(app, users):
    app.state.db.execute("UPDATE users SET enabled=0 WHERE id=?", (users.sam.id,))
    assert notifications.recipients(app.state.db, ["user:sam"], "automation:x") == []


def test_notification_api_and_mark_read(app, users):
    notifications.create(app.state.db, app.state.bus, [users.sam.id], "Power", "UPS on battery", "automation:ups")
    sam = sign_in(lan_client(app), "sam", "pw-sam-1234")
    [n] = sam.get("/api/v1/notifications?unread=true").json()
    assert (n["title"], n["message"], n["source"]) == ("Power", "UPS on battery", "automation:ups")
    assert sam.post("/api/v1/notifications/read", json={"ids": [n["id"]]}).status_code == 204
    assert sam.get("/api/v1/notifications?unread=true").json() == []
    admin = sign_in(lan_client(app), "admin", "pw-admin-1234", users.admin_totp)
    assert admin.get("/api/v1/notifications").json() == []  # only your own


def test_ws_delivers_only_to_recipient(app, client, users):
    sign_in(client, "sam", "pw-sam-1234")
    with connect(client) as ws:
        notifications.create(app.state.db, app.state.bus, [users.admin.id], None, "for admin", "t")
        ping(ws)
        assert ws.receive_json() == {"id": 99, "type": "pong"}
        notifications.create(app.state.db, app.state.bus, [users.sam.id], "Hi", "for sam", "t")
        msg = ws.receive_json()
        assert msg["type"] == "notification" and msg["message"] == "for sam"


def test_message_truncated(app, users):
    notifications.create(app.state.db, app.state.bus, [users.sam.id], "t" * 500, "m" * 5000, "t")
    [n] = notifications.list_for(app.state.db, users.sam.id, unread_only=True)
    assert len(n["title"]) == 120 and n["title"].endswith("…")
    assert len(n["message"]) == 2000 and n["message"].endswith("…")


def live(db):
    bus = EventBus()
    states = StateMachine(bus)
    states.register(Entity("light.a", "A", None, "light"))
    return LiveEffects(states, db, bus, lambda: None), states


def test_live_call_goes_through_state_machine(db):
    fx, states = live(db)
    seen = []

    async def handler(entity_id, command, args):
        seen.append((entity_id, command, args))

    states.set_command_handler("light", handler)
    asyncio.run(fx.call("light.a", "turn_on", {"brightness": 5}))
    assert seen == [("light.a", "turn_on", {"brightness": 5})]


def test_wait_for_state_true_and_timeout(db):
    fx, states = live(db)

    async def go():
        waiter = asyncio.create_task(fx.wait_for_state("light.a", "on", 5))
        await asyncio.sleep(0)
        states.set("light.a", "on")
        hit = await waiter
        already = await fx.wait_for_state("light.a", "on", 5)
        missed = await fx.wait_for_state("light.a", "off", 0.05)
        return hit, already, missed

    assert asyncio.run(go()) == (True, True, False)


def test_script_not_available_yet(db):
    fx, _ = live(db)
    with pytest.raises(ValueError, match="plan 5"):
        asyncio.run(fx.run_script("x.ps1", None, {}))


def test_mqtt_publish_without_mqtt(db):
    fx, _ = live(db)
    with pytest.raises(ValueError, match="MQTT isn't set up"):
        asyncio.run(fx.mqtt_publish("a/b", "x", False))
