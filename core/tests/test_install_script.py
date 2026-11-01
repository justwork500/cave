"""deploy/install.sh --dry-run: the parts that need no Docker. Linux in CI; Git Bash on Windows (no file modes)."""

import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "deploy" / "install.sh"
GIT_BASH = Path("C:/Program Files/Git/bin/bash.exe")
BASH = str(GIT_BASH) if sys.platform == "win32" else shutil.which("bash")

pytestmark = pytest.mark.skipif(not BASH or (sys.platform == "win32" and not GIT_BASH.exists()),
                                reason="needs bash")

ROUTES = {
    "lan": ("192.0.2.1 via 192.168.1.1 dev eth0 src 192.168.1.20 uid 1000",
            "2: eth0    inet 192.168.1.20/24 brd 192.168.1.255 scope global eth0"),
    "docker": ("192.0.2.1 dev docker0 src 172.17.0.1 uid 1000",
               "3: docker0    inet 172.17.0.1/16 brd 172.17.255.255 scope global docker0"),
}


def install(tmp_path: Path, profiles: str = "mqtt,scripts", route: str = "lan", dry_run: bool = True,
            extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    fake = tmp_path / "bin"
    fake.mkdir(exist_ok=True)
    get, addr = ROUTES[route]
    ip = fake / "ip"
    ip.write_text(f'#!/bin/sh\ncase "$*" in\n  *"route get"*) echo "{get}";;\n  *"addr show"*) echo "{addr}";;\n'
                  "esac\n", encoding="utf-8", newline="\n")
    ip.chmod(0o755)
    root = tmp_path / "cave"
    root.mkdir(exist_ok=True)
    env = {**os.environ, "PATH": f"{fake}{os.pathsep}{os.environ['PATH']}", "CAVE_INSTALL_ROOT": root.as_posix(),
           "CAVE_SKIP_CHOWN": "1", **(extra_env or {})}
    flags = ["--dry-run"] if dry_run else []
    return subprocess.run([BASH, SCRIPT.as_posix(), *flags, "--yes", "--profiles", profiles],
                          capture_output=True, text=True, env=env, timeout=60, check=False)


def env_lines(tmp_path: Path) -> dict[str, str]:
    text = (tmp_path / "cave" / ".env").read_text(encoding="utf-8")
    return dict(line.split("=", 1) for line in text.splitlines() if line and not line.startswith("#"))


def test_env_has_lan_not_docker(tmp_path):
    r = install(tmp_path)
    assert r.returncode == 0, r.stderr
    env = env_lines(tmp_path)
    assert env["CAVE_LOCAL_RANGES"] == "192.168.1.0/24" and env["CAVE_HOST_IPS"] == "192.168.1.20"
    assert "localhost" in env["CAVE_HOSTNAMES"]


def test_docker_network_is_never_the_lan(tmp_path):  # Review Focus 1
    r = install(tmp_path, route="docker")
    assert r.returncode != 0 and "CAVE_LOCAL_RANGES" in r.stderr
    assert not (tmp_path / "cave" / ".env").exists()


def test_no_secrets_in_env(tmp_path):
    install(tmp_path)
    text = (tmp_path / "cave" / ".env").read_text(encoding="utf-8")
    assert "TOKEN=" not in text and "PASSWORD=" not in text


def test_secret_files_private(tmp_path):
    install(tmp_path)
    for name in ("runner_token", "mqtt_password"):
        f = tmp_path / "cave" / "secrets" / name
        assert re.fullmatch(r"[0-9a-f]{64}", f.read_text(encoding="utf-8").strip())  # always 32 random bytes
        if sys.platform != "win32":
            assert stat.S_IMODE(f.stat().st_mode) == 0o400
    assert (tmp_path / "cave" / "secrets" / "mosquitto_passwd").exists()
    assert (tmp_path / "cave" / "config" / "mqtt.yaml").read_text(encoding="utf-8").count("username: cave") == 1


def test_rerun_changes_nothing(tmp_path):  # Review Focus 2
    assert install(tmp_path).returncode == 0
    files = [p for p in (tmp_path / "cave").rglob("*") if p.is_file()]
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in files}
    assert install(tmp_path).returncode == 0
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in files} == before
    assert sorted(p for p in (tmp_path / "cave").rglob("*") if p.is_file()) == sorted(files)


def test_scripts_profile_sets_runner_url(tmp_path):
    install(tmp_path, profiles="mqtt")
    assert env_lines(tmp_path)["CAVE_RUNNER_URL"] == ""
    assert env_lines(tmp_path)["COMPOSE_PROFILES"] == "mqtt"
    other = tmp_path / "second"
    other.mkdir()
    install(other, profiles="mqtt,scripts")
    assert env_lines(other)["CAVE_RUNNER_URL"] == "http://script-runner:8099"


FAKE_DOCKER = """#!/bin/sh
echo "docker $*" >> "$CAVE_FAKE_LOG"
case "$*" in
  "compose version") exit 0 ;;
  "compose config --images mosquitto")
    [ -f .env ] || { echo "env file .env not found" >&2; exit 1; }  # compose.yaml has env_file: .env
    echo "eclipse-mosquitto:2@sha256:abc" ;;
  "compose ps -q cave") echo cid ;;
  inspect*) echo healthy ;;
  "compose logs cave") echo "cave-1  | CAVE isn't set up yet. Open it in a browser and use this one-time setup code: AAAA-BBBB" ;;
  run*) cat >/dev/null; chmod u+w "$CAVE_FAKE_PASSWD"; echo 'cave:$7$101$hash' >> "$CAVE_FAKE_PASSWD" ;;  # root in the container, like mosquitto_passwd -U
esac
exit 0
"""


def test_full_install_with_fake_docker(tmp_path):
    """The real run, with Docker faked: .env exists before Compose is asked anything, and the MQTT password never
    goes on a command line (where ps and docker inspect would show it)."""
    fake = tmp_path / "bin"
    fake.mkdir()
    for name, text in (("docker", FAKE_DOCKER), ("sudo", '#!/bin/sh\nexec "$@"\n')):
        (fake / name).write_text(text, encoding="utf-8", newline="\n")
        (fake / name).chmod(0o755)
    log = tmp_path / "docker.log"
    env = {"CAVE_FAKE_LOG": log.as_posix(),
           "CAVE_FAKE_PASSWD": (tmp_path / "cave" / "secrets" / "mosquitto_passwd").as_posix()}
    install(tmp_path, dry_run=False, extra_env=env)
    r = install(tmp_path, dry_run=False, extra_env=env)  # and again: nothing new
    assert r.returncode == 0, r.stderr
    calls = log.read_text(encoding="utf-8")
    password = (tmp_path / "cave" / "secrets" / "mqtt_password").read_text(encoding="utf-8").strip()
    assert "eclipse-mosquitto:2@sha256:abc" in calls and password not in calls
    assert calls.count("docker run") == 1  # the cave user is created once
    assert "AAAA-BBBB" in r.stdout
