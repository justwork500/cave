import pytest

from cave.access import netconfig
from cave.access.items import set_assignments
from cave.api.app import create_app
from cave.settings import Settings
from tests.conftest import lan_client, sign_in


def as_admin(client, users):
    return sign_in(client, "admin", "pw-admin-1234", users.admin_totp)


def test_save_normalizes_and_audits(db):
    cfg = netconfig.save(db, "user:a", ["192.168.1.7/24", "fd00::/8"], ["192.168.1.1"])
    assert cfg.local_ranges == ("192.168.1.0/24", "fd00::/8")
    assert cfg.trusted_proxies == ("192.168.1.1/32",)
    assert netconfig.load(db) == cfg
    row = db.execute("SELECT action FROM audit ORDER BY id DESC").fetchone()
    assert row["action"] == "network.update"


def test_invalid_range_rejected_and_nothing_stored(client, users):  # Review Focus 4
    as_admin(client, users)
    before = client.get("/api/v1/system/networks").json()
    r = client.put("/api/v1/system/networks", json={"local_ranges": ["10.0.0.0/8", "nope"], "trusted_proxies": []})
    assert r.status_code == 422 and r.json() == {"detail": "Not a valid address range: nope"}
    assert client.get("/api/v1/system/networks").json() == before


def test_save_raises_invalid_range(db):
    with pytest.raises(netconfig.InvalidRange) as e:
        netconfig.save(db, "a", ["300.1.1.1/24"], [])
    assert e.value.value == "300.1.1.1/24"


def test_seed_runs_once(tmp_path):
    s = Settings(db_path=tmp_path / "s.db", config_dir=tmp_path, local_ranges=["192.168.1.0/24"])
    app = create_app(s)
    netconfig.save(app.state.db, "user:a", ["10.0.0.0/8"], [])
    app.state.db.close()
    app = create_app(s)
    assert netconfig.load(app.state.db).local_ranges == ("10.0.0.0/8",)
    app.state.db.close()


def test_seed_detects_when_no_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(netconfig, "detect_local_ranges", lambda: ["172.16.5.0/24"])
    app = create_app(Settings(db_path=tmp_path / "d.db", config_dir=tmp_path))
    assert netconfig.load(app.state.db).local_ranges == ("172.16.5.0/24",)
    app.state.db.close()


def test_container_never_detects_its_own_network(tmp_path, monkeypatch):  # Plan 7 Review Focus 1
    """Inside a container the detected /24 is Docker's bridge, which holds the gateway every proxied request comes
    from: seeding it would make everyone "local". With no ranges given, seed none, so Local only fails closed."""
    from cave.envconfig import settings_from_env

    monkeypatch.setattr(netconfig, "detect_local_ranges", lambda: ["172.18.0.0/24"])
    settings = settings_from_env(tmp_path, tmp_path, {"CAVE_IN_CONTAINER": "1", "CAVE_LOCAL_RANGES": ""})
    app = create_app(settings)
    assert netconfig.load(app.state.db).local_ranges == ()
    app.state.db.close()


def test_operator_cannot_change_networks(client, users):
    sign_in(client, "op", "pw-op-1234", users.op_totp)
    assert client.get("/api/v1/system/networks").status_code == 403
    assert client.put("/api/v1/system/networks", json={"local_ranges": [], "trusted_proxies": []}).status_code == 403


def test_networks_change_applies_immediately(app, client, users, garage):
    set_assignments(app.state.db, "test", "dashboard:garage", [("user", users.sam.id)])
    sam = sign_in(lan_client(app, "10.9.9.9"), "sam", "pw-sam-1234")
    assert sam.post("/api/v1/entities/cover.garage_door/commands/open", json={}).status_code == 403
    as_admin(client, users)
    r = client.put("/api/v1/system/networks", json={"local_ranges": ["192.168.1.0/24", "10.9.9.0/24"],
                                                     "trusted_proxies": []})
    assert r.status_code == 200
    assert sam.post("/api/v1/entities/cover.garage_door/commands/open", json={}).status_code == 202


def test_xff_multiple_header_lines_joined(app, users, garage):
    netconfig.save(app.state.db, "test", ["192.168.1.0/24"], ["192.168.1.1/32"])
    set_assignments(app.state.db, "test", "dashboard:garage", [("user", users.sam.id)])
    sam = sign_in(lan_client(app, "192.168.1.1"), "sam", "pw-sam-1234")
    # first line claims a LAN client; the proxy's own appended line names the real (outside) one
    r = sam.post(
        "/api/v1/entities/cover.garage_door/commands/open",
        json={},
        headers=[("x-forwarded-for", "192.168.1.50"), ("x-forwarded-for", "203.0.113.9")],
    )
    assert r.status_code == 403


def test_certificate_404_without_cert(client, users):
    as_admin(client, users)
    assert client.get("/api/v1/system/certificate").status_code == 404


def test_certificate_reports_fingerprint(app, client, users, tmp_path):
    from cave import tls

    cert, _ = tls.ensure_certificate(tmp_path / "tls", ["cave.local"], [])
    app.state.cert_path = cert
    as_admin(client, users)
    body = client.get("/api/v1/system/certificate").json()
    assert body["fingerprint"] == tls.fingerprint(cert) and body["self_signed"] is True and body["not_after"]
