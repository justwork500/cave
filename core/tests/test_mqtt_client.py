import asyncio
import os

import aiomqtt
import pytest
from fastapi.testclient import TestClient

from cave.integrations.mqtt import client as client_mod
from cave.integrations.mqtt.client import MqttService, backoff
from cave.integrations.mqtt.config import Broker, MqttConfig
from cave.state import EventBus, StateMachine
from tests.conftest import sign_in
from tests.mqtt_fixtures import fixture


def test_backoff_schedule():
    assert [backoff(n) for n in range(8)] == [1, 2, 4, 8, 16, 32, 60, 60]


def test_status_disabled_without_config(client, users):
    sign_in(client, "admin", "pw-admin-1234", users.admin_totp)
    assert client.get("/api/v1/system/mqtt").json() == {
        "status": "disabled", "broker": None, "last_error": None, "entities": 0, "unsupported": []}


def test_status_needs_devices_or_system(client, users):
    sign_in(client, "sam", "pw-sam-1234")
    assert client.get("/api/v1/system/mqtt").status_code == 403


def test_bad_config_reports_failed(app, users, tmp_path):
    (tmp_path / "mqtt.yaml").write_text("broker:\n  host: x\n  colour: red\n", encoding="utf-8")
    with TestClient(app, base_url="https://testserver", client=("192.168.1.5", 50000)) as c:
        sign_in(c, "admin", "pw-admin-1234", users.admin_totp)
        body = c.get("/api/v1/system/mqtt").json()
    assert body["status"] == "failed" and "colour" in body["last_error"]


class _Msg:
    def __init__(self, topic: str, payload: bytes) -> None:
        self.topic = aiomqtt.Topic(topic)
        self.payload = payload


def test_service_feeds_bridge(db, monkeypatch):
    seen_status: list[str] = []
    clients: list = []
    service_box: list[MqttService] = []

    class FakeClient:
        def __init__(self, hostname, port, **kwargs):
            self.hostname, self.port, self.kwargs, self.subs = hostname, port, kwargs, []
            clients.append(self)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def subscribe(self, topic):
            self.subs.extend(t for t, _qos in topic)

        async def publish(self, topic, payload=None, qos=0, retain=False):
            pass

        @property
        def messages(self):
            async def gen():
                seen_status.append(service_box[0].status)
                yield _Msg(*fixture("z2m_light_json"))
                yield _Msg("zigbee2mqtt/Kitchen lamp", b'{"state": "ON"}')
                raise aiomqtt.MqttError("connection lost")

            return gen()

    monkeypatch.setattr(client_mod.aiomqtt, "Client", FakeClient)
    monkeypatch.setattr(client_mod, "backoff", lambda n: 30)
    states = StateMachine(EventBus())
    service = MqttService(MqttConfig(Broker("broker.lan", 1884, "cave")), db, states, "secret")
    service_box.append(service)

    async def go():
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(service.run(), 0.5)

    asyncio.run(go())
    assert seen_status == ["connected"]
    assert service.status == "connecting" and "connection lost" in service.last_error
    c = clients[0]
    assert (c.hostname, c.port, c.kwargs["username"], c.kwargs["password"]) == ("broker.lan", 1884, "cave", "secret")
    assert {"homeassistant/+/+/config", "homeassistant/+/+/+/config", "zigbee2mqtt/Kitchen lamp"} <= set(c.subs)
    assert states.get("light.kitchen_lamp").value == "on"


def test_publish_while_disconnected_is_refused(db):
    service = MqttService(MqttConfig(Broker("x")), db, StateMachine(EventBus()), None)
    with pytest.raises(ValueError, match="isn't connected"):
        asyncio.run(service.bridge.publish("a/b", "x"))


@pytest.mark.skipif(not os.environ.get("CAVE_MQTT_TEST_BROKER"), reason="set CAVE_MQTT_TEST_BROKER=host:port")
def test_live_broker_roundtrip(db):
    host, port = os.environ["CAVE_MQTT_TEST_BROKER"].rsplit(":", 1)
    states = StateMachine(EventBus())
    user, password = os.environ.get("CAVE_MQTT_TEST_USER"), os.environ.get("CAVE_MQTT_PASSWORD")  # the Compose broker
    service = MqttService(MqttConfig(Broker(host, int(port), username=user)), db, states, password)

    async def go():
        task = asyncio.create_task(service.run())
        async with aiomqtt.Client(host, int(port), username=user, password=password) as pub:
            await asyncio.sleep(0.5)
            topic, payload = fixture("z2m_light_json")
            await pub.publish(topic, payload, retain=True)
            await pub.publish("zigbee2mqtt/Kitchen lamp", b'{"state": "ON"}')
            await asyncio.sleep(0.5)
            await pub.publish(topic, b"", retain=True)  # clean up the retained config
        task.cancel()

    asyncio.run(go())
    assert states.get("light.kitchen_lamp").value == "on"
