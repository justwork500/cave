from cave.db import Database


def test_open_is_idempotent_and_wal(tmp_path):
    Database.open(tmp_path / "c.db").close()
    db = Database.open(tmp_path / "c.db")
    assert db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert db.execute("PRAGMA user_version").fetchone()[0] == 7
    db.close()


def test_foreign_keys_on(db):
    assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_migrations_apply_in_order(tmp_path):
    db = Database.open(tmp_path / "m.db")
    assert db.execute("PRAGMA user_version").fetchone()[0] == 7
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


def test_parallel_reads_never_mix_rows(tmp_path):
    """Request threads share one connection; each must get its own statement's rows (it once gave wrong 401s)."""
    import threading

    db = Database.open(tmp_path / "t.db")
    db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    for i in range(100):
        db.execute("INSERT INTO t VALUES (?, ?)", (i, f"v{i}"))
    problems: list[str] = []

    def work(seed: int) -> None:
        for n in range(300):
            i = (seed * 37 + n) % 100
            try:
                row = db.execute("SELECT v FROM t WHERE id=?", (i,)).fetchone()
                if row is None or row["v"] != f"v{i}":
                    problems.append(f"{i}: {row and tuple(row)}")
                if n % 5 == 0:
                    db.execute("UPDATE t SET v=? WHERE id=?", (f"v{i}", i))
            except Exception as e:  # noqa: BLE001 - any error here is the bug
                problems.append(repr(e))

    threads = [threading.Thread(target=work, args=(s,)) for s in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    db.close()
    assert problems == []


def test_execute_keeps_cursor_facts(tmp_path):
    db = Database.open(tmp_path / "t.db")
    db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    ins = db.execute("INSERT INTO t (v) VALUES ('a')")
    assert ins.lastrowid == 1 and ins.rowcount == 1
    db.execute("INSERT INTO t (v) VALUES ('b')")
    assert [r["v"] for r in db.execute("SELECT v FROM t ORDER BY id")] == ["a", "b"]
    rows = db.execute("SELECT v FROM t ORDER BY id")
    assert rows.fetchone()["v"] == "a" and rows.fetchall()[0]["v"] == "b" and rows.fetchone() is None
    assert db.execute("UPDATE t SET v='c'").rowcount == 2
    db.close()
