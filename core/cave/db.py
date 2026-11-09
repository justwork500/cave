"""SQLite access and the numbered schema migrations in cave/migrations."""

import sqlite3
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from importlib.resources import files
from pathlib import Path
from typing import Any


def _migrations() -> list[tuple[int, str]]:
    """(version, sql) for every migrations/NNNN_*.sql file, in order."""
    found = []
    for f in files("cave.migrations").iterdir():
        if f.name.endswith(".sql"):
            found.append((int(f.name.split("_", 1)[0]), f.read_text()))
    return sorted(found)


class Result:
    """A statement's rows and cursor facts, all read while the connection was locked."""

    def __init__(self, cur: sqlite3.Cursor) -> None:
        self._rows: list[sqlite3.Row] = cur.fetchall()
        self.rowcount, self.lastrowid = cur.rowcount, cur.lastrowid
        self._next = 0

    def fetchone(self) -> Any:
        if self._next >= len(self._rows):
            return None
        self._next += 1
        return self._rows[self._next - 1]

    def fetchall(self) -> list[Any]:
        rest, self._next = self._rows[self._next:], len(self._rows)
        return rest

    def __iter__(self) -> Iterator[Any]:
        return iter(self.fetchall())


class Database:
    """One SQLite connection shared across threads, serialized by a lock."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._lock = threading.RLock()

    @classmethod
    def open(cls, path: Path) -> "Database":
        conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        db = cls(conn)
        db._migrate()
        return db

    def _migrate(self) -> None:
        current = self.execute("PRAGMA user_version").fetchone()[0]
        for version, sql in _migrations():
            if version <= current:
                continue
            with self.transaction() as conn:
                for statement in sql.split(";"):
                    if statement.strip():
                        conn.execute(statement)
                conn.execute(f"PRAGMA user_version={version}")

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def execute(self, sql: str, params: Sequence[Any] = ()) -> "Result":
        with self._lock:
            # rows are read before the lock is released: a cursor stepped later would race other threads
            return Result(self._conn.execute(sql, params))

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield self._conn
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            self._conn.execute("COMMIT")
