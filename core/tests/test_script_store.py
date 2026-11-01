from cave import audit
from cave.access.items import get_item, set_assignments
from tests.conftest import lan_client, sign_in

PLAIN = "#!/usr/bin/env bash\n# cave:\n#   name: Disk report\necho '{\"ok\": true}'\n"
SECRET = "# cave:\n#   name: Uses a token\n#   secrets: [PROXMOX_TOKEN]\nimport json\nprint(json.dumps({}))\n"


def put(app, name, text):
    d = app.state.settings.config_dir / "scripts"
    d.mkdir(exist_ok=True)
    (d / name).write_bytes(text.encode())


def as_admin(app, users):
    return sign_in(lan_client(app), "admin", "pw-admin-1234", users.admin_totp)


def as_op(app, users):
    return sign_in(lan_client(app), "op", "pw-op-1234", users.op_totp)


def test_load_creates_items(app, users):
    put(app, "disk.sh", PLAIN)
    put(app, "notes.txt", "ignored")
    app.state.scripts.load_all()
    item = get_item(app.state.db, "script:disk.sh")
    assert item is not None and item.kind == "action" and item.name == "Disk report"
    assert [s["file"] for s in as_admin(app, users).get("/api/v1/scripts").json()] == ["disk.sh"]


def test_bad_header_listed_in_config_errors_with_line(app, users):
    put(app, "bad.py", "# cave:\n#   name: Bad\n#   colour: red\n")
    app.state.scripts.load_all()
    errors = as_admin(app, users).get("/api/v1/config/errors").json()
    assert errors["scripts/bad.py"].startswith("bad.py:3: ")


def test_operator_with_scripts_section_can_save_plain_script(app, users):
    r = as_op(app, users).put("/api/v1/scripts/disk.sh", json={"text": PLAIN})
    assert r.status_code == 200, r.text
    assert app.state.scripts.get("disk.sh") is not None


def test_secrets_need_admin_new_and_existing(app, users):
    op = as_op(app, users)
    r = op.put("/api/v1/scripts/token.py", json={"text": SECRET})
    assert r.status_code == 403 and "secrets" in r.json()["detail"]
    assert as_admin(app, users).put("/api/v1/scripts/token.py", json={"text": SECRET}).status_code == 200
    harmless = SECRET.replace("#   secrets: [PROXMOX_TOKEN]\n", "")
    assert op.put("/api/v1/scripts/token.py", json={"text": harmless}).status_code == 403
    assert op.delete("/api/v1/scripts/token.py").status_code == 403


def test_bad_header_is_422_with_line(app, users):
    r = as_op(app, users).put("/api/v1/scripts/x.sh", json={"text": "# cave:\n#   name: X\n#   target: cave-host\n"})
    assert r.status_code == 422 and r.json()["detail"].startswith("x.sh:3: ")


def test_household_cannot_edit(app, users):
    sam = sign_in(lan_client(app), "sam", "pw-sam-1234")
    assert sam.put("/api/v1/scripts/disk.sh", json={"text": PLAIN}).status_code == 403
    assert sam.get("/api/v1/scripts").status_code == 403


def test_path_tricks_404(app, users):  # Review Focus 1
    c = as_admin(app, users)
    for name in ("..%2Fx.sh", "x.exe", "a..b.py", "..sh"):
        assert c.put(f"/api/v1/scripts/{name}", json={"text": PLAIN}).status_code in (404, 405), name
        assert c.get(f"/api/v1/scripts/{name}").status_code == 404, name
    assert not (app.state.settings.config_dir / "x.sh").exists()


def test_save_keeps_bytes_and_audits_old_and_new(app, users):
    c = as_admin(app, users)
    crlf = PLAIN.replace("\n", "\r\n")
    c.put("/api/v1/scripts/disk.sh", json={"text": PLAIN})
    c.put("/api/v1/scripts/disk.sh", json={"text": crlf})
    assert (app.state.settings.config_dir / "scripts" / "disk.sh").read_bytes() == crlf.encode()
    entry = next(e for e in audit.list_entries(app.state.db) if e["action"] == "config.save")
    assert entry["old"] == PLAIN and entry["new"] == crlf
    got = c.get("/api/v1/scripts/disk.sh").json()
    assert got["language"] == "bash" and got["header"]["name"] == "Disk report" and got["text"] == crlf


def test_delete_keeps_item(app, users):
    c = as_admin(app, users)
    c.put("/api/v1/scripts/disk.sh", json={"text": PLAIN})
    set_assignments(app.state.db, "test", "script:disk.sh", [("role", "household")])
    assert c.delete("/api/v1/scripts/disk.sh").status_code == 204
    assert get_item(app.state.db, "script:disk.sh") is not None and app.state.scripts.get("disk.sh") is None
