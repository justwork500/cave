"""Static checks on the Dockerfiles: no Docker needed."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "deploy" / "core" / "Dockerfile"
RUNNER = ROOT / "deploy" / "script-runner" / "Dockerfile"


def froms(path: Path) -> list[str]:
    return re.findall(r"^FROM\s+(\S+)", path.read_text(encoding="utf-8"), re.MULTILINE)


def test_base_images_pinned_by_digest():
    for path in (CORE, RUNNER):
        images = froms(path)
        assert images, path
        for image in images:
            assert "@sha256:" in image and ":latest" not in image, f"{path.name}: {image}"


def test_core_runs_as_non_root():
    text = CORE.read_text(encoding="utf-8")
    runtime = text[text.rindex("FROM "):]  # the last stage is what runs
    users = re.findall(r"^USER\s+(\S+)", runtime, re.MULTILINE)
    assert users and users[-1] not in ("root", "0", "0:0")
    assert "HEALTHCHECK" in runtime and '"cave", "health"' in runtime
    # stdout is a pipe in a container: unbuffered, or the setup code never reaches docker compose logs
    assert "PYTHONUNBUFFERED=1" in runtime
    assert "CAVE_IN_CONTAINER=1" in runtime  # no LAN detection in here: it would find Docker's network


def test_runner_has_no_docker_socket_and_checks_pwsh_download():
    text = RUNNER.read_text(encoding="utf-8")
    assert "docker.sock" not in text
    assert "TARGETARCH" in text and "sha256sum -c" in text


def test_dockerignore_keeps_secrets_and_junk_out():
    lines = set((ROOT / ".dockerignore").read_text(encoding="utf-8").split())
    assert {"**/node_modules", "**/.venv", "data", "secrets", ".env", ".git"} <= lines


def test_core_gets_host_key_as_a_secret():
    import yaml
    services = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))["services"]
    cave = services["cave"]
    assert "host_key" in cave["secrets"]
    assert cave["environment"]["CAVE_HOST_KEY_FILE"] == "/run/secrets/host_key"
    for svc in services.values():
        assert "CAVE_HOST_KEY" not in (svc.get("environment") or {})
