"""Static checks on compose.yaml: the security properties the stack promises. No Docker needed."""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def compose():
    return yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))


def test_runner_is_unreachable_from_outside(compose):
    runner = compose["services"]["script-runner"]
    assert "ports" not in runner and "expose" not in runner
    assert runner["networks"] == ["runner"]
    assert compose["networks"]["runner"]["internal"] is True
    assert "runner" in compose["services"]["cave"]["networks"]


def test_no_secret_values_in_environment(compose):
    for name, svc in compose["services"].items():
        env = svc.get("environment", {})
        assert isinstance(env, dict), name
        for key in env:
            if key.endswith(("TOKEN", "PASSWORD")):
                pytest.fail(f"{name} passes {key} as a value; use a secret file and {key}_FILE")
    assert set(compose["secrets"]) == {"mqtt_password", "runner_token"}
    assert all("file" in s for s in compose["secrets"].values())


def test_hardening(compose):
    cave, runner = compose["services"]["cave"], compose["services"]["script-runner"]
    for svc in (cave, runner):
        assert svc["read_only"] is True and svc["cap_drop"] == ["ALL"]
        assert "no-new-privileges:true" in svc["security_opt"]
    assert "cap_add" not in cave
    # DAC_OVERRIDE: root in the runner reads the token (owned by cave's uid, 0400) and enters each run's 0700
    # folder before switching to the script user, who doesn't keep it
    assert set(runner["cap_add"]) == {"SETUID", "SETGID", "KILL", "CHOWN", "DAC_OVERRIDE"}
    assert runner["mem_limit"] and runner["cpus"] and runner["pids_limit"]
    assert "./config/scripts:/scripts:ro" in runner["volumes"]


def test_no_docker_socket(compose):
    for name, svc in compose["services"].items():
        assert not any("docker.sock" in str(v) for v in svc.get("volumes", [])), name


def test_offline_restart(compose):
    for name, svc in compose["services"].items():
        if "build" in svc:
            assert svc["pull_policy"] == "never" and svc["image"].endswith(":local"), name
        else:
            assert "@sha256:" in svc["image"], name


def test_profiles(compose):
    s = compose["services"]
    assert "profiles" not in s["cave"]
    assert s["mosquitto"]["profiles"] == ["mqtt"] and s["script-runner"]["profiles"] == ["scripts"]
