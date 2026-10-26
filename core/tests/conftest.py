from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cave.db import Database

T0 = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    d = Database.open(tmp_path / "t.db")
    yield d
    d.close()
