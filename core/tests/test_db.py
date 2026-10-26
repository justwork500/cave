from cave.db import Database


def test_open_is_idempotent_and_wal(tmp_path):
    Database.open(tmp_path / "c.db").close()
    db = Database.open(tmp_path / "c.db")
    assert db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert db.execute("PRAGMA user_version").fetchone()[0] == 1
    db.close()


def test_foreign_keys_on(db):
    assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
