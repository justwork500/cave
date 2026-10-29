import json
from pathlib import Path

from cave.config.models import schema_files

SCHEMAS = Path(__file__).resolve().parents[2] / "schemas"


def test_schemas_committed_match_generated():
    for name, schema in schema_files().items():
        committed = json.loads((SCHEMAS / name).read_text(encoding="utf-8"))
        assert committed == schema, f"schemas/{name} is stale: run `python -m cave schemas`"
