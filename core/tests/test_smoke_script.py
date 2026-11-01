"""deploy/smoke.py runs as whoever ran the installer, after data/ was handed to the container's uid."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load():
    spec = importlib.util.spec_from_file_location("smoke", ROOT / "deploy" / "smoke.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_state_file_is_outside_the_containers_folders():
    default = load().STATE_DEFAULT
    assert default.parts[0] not in ("data", "config", "secrets")
    assert str(default) in (ROOT / ".gitignore").read_text(encoding="utf-8").split()
