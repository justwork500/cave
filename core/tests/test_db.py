from cave.db import Database


def test_open_is_idempotent_and_wal(tmp_path):
    Database.open(tmp_path / "c.db").close()
    db = Database.open(tmp_path / "c.db")
    assert db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert db.execute("PRAGMA user_version").fetchone()[0] == 1
    db.close()


def test_foreign_keys_on(db):
    assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_migrations_apply_in_order(tmp_path):
    db = Database.open(tmp_path / "m.db")
    assert db.execute("PRAGMA user_version").fetchone()[0] == 1
    assert db.execute("SELECT count(*) FROM sqlite_master WHERE name='users'").fetchone()[0] == 1
    db.close()


def test_existing_v1_db_is_upgraded_not_recreated(tmp_path):
    from cave.auth.users import create_user

    db = Database.open(tmp_path / "u.db")
    create_user(db, "system", "sam", "pw-sam-1234", "household")
    db.close()
    db = Database.open(tmp_path / "u.db")
    assert db.execute("SELECT count(*) FROM users").fetchone()[0] == 1
    db.close()
