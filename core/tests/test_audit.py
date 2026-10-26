from cave import audit


def test_audit_records_old_and_new(db):
    audit.record(db, "user:1", "item.update", "item:home", {"visibility": "show"}, {"visibility": "restrict"})
    e = audit.list_entries(db)[0]
    assert (e["actor"], e["action"], e["target"]) == ("user:1", "item.update", "item:home")
    assert e["old"] == {"visibility": "show"} and e["new"] == {"visibility": "restrict"}


def test_audit_newest_first(db):
    audit.record(db, "a", "x.one", "t")
    audit.record(db, "a", "x.two", "t")
    assert [e["action"] for e in audit.list_entries(db)] == ["x.two", "x.one"]
