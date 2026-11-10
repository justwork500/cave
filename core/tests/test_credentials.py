import logging
import os
import re
import sys

import pytest

from cave import audit
from cave.credentials import Credentials, load_host_key

KEY = bytes(range(32))
VALUE = "s3cret-value"


@pytest.fixture
def creds(db):
    return Credentials(db, KEY)


def test_round_trip(creds):
    creds.set("hue", "abc:app_key", VALUE, "user:admin")
    assert creds.get("hue", "abc:app_key") == VALUE
    assert creds.is_set("hue", "abc:app_key")
    assert creds.get("hue", "missing") is None and not creds.is_set("hue", "missing")


def test_stored_encrypted(db, creds):
    creds.set("hue", "abc:app_key", VALUE, "user:admin")
    row = db.execute("SELECT nonce, ciphertext FROM credentials").fetchone()
    assert VALUE.encode() not in row["ciphertext"] and VALUE.encode() not in row["nonce"]


def test_rows_cannot_be_swapped(db, creds):
    creds.set("hue", "a", VALUE, "user:admin")
    creds.set("hue", "b", "other", "user:admin")
    row = db.execute("SELECT nonce, ciphertext FROM credentials WHERE name = 'a'").fetchone()
    db.execute("UPDATE credentials SET nonce = ?, ciphertext = ? WHERE name = 'b'", (row["nonce"], row["ciphertext"]))
    assert creds.get("hue", "b") is None


def test_wrong_key_reads_as_not_set(db, creds, caplog):
    creds.set("hue", "abc:app_key", VALUE, "user:admin")
    other = bytes(32)
    with caplog.at_level(logging.WARNING):
        assert Credentials(db, other).get("hue", "abc:app_key") is None
        assert not Credentials(db, other).is_set("hue", "abc:app_key")
    assert "hue:abc:app_key" in caplog.text
    assert KEY.hex() not in caplog.text and other.hex() not in caplog.text and VALUE not in caplog.text


def test_audit_masks_value(db, creds):
    creds.set("hue", "abc:app_key", VALUE, "user:admin")
    e = audit.list_entries(db)[0]
    assert (e["action"], e["target"], e["new"]) == ("credential.set", "credential:hue:abc:app_key", {"set": True})
    assert VALUE not in str(audit.list_entries(db))


def test_delete_audited(db, creds):
    creds.set("hue", "a", VALUE, "user:admin")
    creds.delete("hue", "a", "user:admin")
    e = audit.list_entries(db)[0]
    assert (e["action"], e["old"], e["new"]) == ("credential.delete", {"set": True}, {"set": False})
    assert not creds.is_set("hue", "a")


def test_delete_prefix(creds):
    for n in ("abc:app_key", "abc:pw", "other:app_key"):
        creds.set("hue", n, VALUE, "user:admin")
    creds.delete_prefix("hue", "abc:", "user:admin")
    assert not creds.is_set("hue", "abc:app_key") and not creds.is_set("hue", "abc:pw")
    assert creds.is_set("hue", "other:app_key")


def test_host_key_file_created_once(tmp_path):
    k = load_host_key(tmp_path / "cave.db", {})
    f = tmp_path / "host_key"
    assert len(k) == 32 and re.fullmatch(r"[0-9a-f]{64}", f.read_text(encoding="utf-8"))
    if sys.platform != "win32":
        assert os.stat(f).st_mode & 0o777 == 0o600
    assert load_host_key(tmp_path / "cave.db", {}) == k


def test_host_key_from_env_file(tmp_path):
    src = tmp_path / "secret"
    src.write_text(KEY.hex() + "\n", encoding="utf-8")
    assert load_host_key(tmp_path / "data" / "cave.db", {"CAVE_HOST_KEY_FILE": str(src)}) == KEY
    assert not (tmp_path / "data" / "host_key").exists()


def test_malformed_host_key_exits(tmp_path):
    with pytest.raises(SystemExit) as e:
        load_host_key(tmp_path / "cave.db", {"CAVE_HOST_KEY": "nothex"})
    assert "CAVE_HOST_KEY" in str(e.value) and "nothex" not in str(e.value)


def test_malformed_host_key_file_exits(tmp_path):
    (tmp_path / "host_key").write_text("nothex", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        load_host_key(tmp_path / "cave.db", {})
    assert "host_key" in str(e.value) and "nothex" not in str(e.value)
