import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "mqtt"


def fixture(name: str) -> tuple[str, bytes]:
    """(topic, payload bytes) for a discovery fixture."""
    data = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    return data["topic"], json.dumps(data["payload"]).encode()


def with_payload(name: str, **changes: object) -> tuple[str, bytes]:
    data = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    data["payload"].update(changes)
    return data["topic"], json.dumps(data["payload"]).encode()
