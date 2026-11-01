from pathlib import Path

import pytest

from cave.envconfig import cert_names, cert_paths, env_secret, settings_from_env


def test_env_secret_prefers_file(tmp_path):
    f = tmp_path / "s"
    f.write_text("s3cret\n", encoding="utf-8")
    assert env_secret("X", {"X_FILE": str(f), "X": "other"}) == "s3cret"


def test_env_secret_plain_value_and_empty():
    assert env_secret("X", {"X": "v"}) == "v"
    assert env_secret("X", {"X": ""}) is None
    assert env_secret("X", {}) is None


def test_env_secret_missing_file_exits_without_contents(tmp_path):
    with pytest.raises(SystemExit) as e:
        env_secret("X", {"X_FILE": str(tmp_path / "nope")})
    assert "X_FILE" in str(e.value)


def test_settings_from_env_ranges():
    s = settings_from_env(Path("d"), Path("c"), {"CAVE_LOCAL_RANGES": "192.168.1.0/24, 10.0.0.0/8",
                                                   "CAVE_TRUSTED_PROXIES": "192.168.1.5"})
    assert s.local_ranges == ["192.168.1.0/24", "10.0.0.0/8"] and s.trusted_proxies == ["192.168.1.5/32"]
    assert s.db_path == Path("d") / "cave.db" and s.config_dir == Path("c")
    with pytest.raises(SystemExit) as e:
        settings_from_env(Path("d"), Path("c"), {"CAVE_LOCAL_RANGES": "192.168.1.300/24"})
    assert "CAVE_LOCAL_RANGES" in str(e.value) and "192.168.1.300/24" in str(e.value)


def test_unset_ranges_keep_detection():
    s = settings_from_env(Path("d"), Path("c"), {})
    assert s.local_ranges == [] and s.trusted_proxies == []  # netconfig.seed then detects the LAN


def test_cert_names_from_env():
    names, ips = cert_names({"CAVE_HOSTNAMES": "cave.lan cave", "CAVE_HOST_IPS": "192.168.1.20"})
    assert names == ["cave.lan", "cave", "localhost"]
    assert ips == ["192.168.1.20", "127.0.0.1"]
    with pytest.raises(SystemExit):
        cert_names({"CAVE_HOST_IPS": "not-an-ip"})


def test_own_cert_from_env(tmp_path):
    assert cert_paths(None, None, {}) is None  # self-signed
    assert cert_paths(None, None, {"CAVE_CERT": "/c.pem", "CAVE_KEY": "/k.pem"}) == (Path("/c.pem"), Path("/k.pem"))
    assert cert_paths(Path("/a"), Path("/b"), {"CAVE_CERT": "/c.pem", "CAVE_KEY": "/k.pem"}) == (Path("/a"), Path("/b"))
    with pytest.raises(SystemExit) as e:
        cert_paths(None, None, {"CAVE_CERT": "/c.pem"})
    assert "go together" in str(e.value)
