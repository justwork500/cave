import pytest

from cave.access.evaluate import evaluate
from cave.access.items import get_assignments, get_item, seed_builtins, set_assignments, upsert_item
from cave.access.model import Decision
from tests.access_fixtures import LAN, LOCAL, PRINCIPALS, WAN, item, token_of

CASES = [
    ("sam", {}, [], LAN, Decision(False, True)),
    ("sam", {"others_see": "none"}, [], LAN, Decision(False, False)),
    ("sam", {}, [("user", "sam")], LAN, Decision(True, True)),
    ("sam", {}, [("group", "family")], LAN, Decision(True, True)),
    ("sam", {}, [("role", "household")], LAN, Decision(True, True)),
    ("sam", {}, [("role", "operator")], LAN, Decision(False, True)),
    ("sam", {"visibility": "hide"}, [("user", "sam")], LAN, Decision(False, False)),
    ("sam", {"visibility": "show"}, [], LAN, Decision(True, True)),
    ("sam", {"status": "disabled", "visibility": "show"}, [], LAN, Decision(False, True)),
    ("sam", {"status": "disabled"}, [], LAN, Decision(False, False)),
    ("sam_disabled", {"visibility": "show"}, [], LAN, Decision(False, False)),
    ("garage_tablet", {"network": "local"}, [("screen", "garage")], LAN, Decision(True, True)),
    ("garage_tablet", {"network": "local"}, [("screen", "garage")], WAN, Decision(False, True)),
    ("other_tablet", {"network": "local"}, [("screen", "garage")], LAN, Decision(False, True)),
    ("sam", {"network": "local", "visibility": "hide"}, [], WAN, Decision(False, False)),
    ("admin", {"visibility": "hide"}, [], WAN, Decision(True, True)),
    ("admin", {"status": "disabled"}, [], LAN, Decision(False, True)),
]


@pytest.mark.parametrize(("who", "overrides", "assigned", "ip", "expected"), CASES)
def test_evaluate(db, who, overrides, assigned, ip, expected):
    it = item(**overrides)
    upsert_item(db, "test", it)
    set_assignments(db, "test", it.id, assigned)
    assert evaluate(db, PRINCIPALS[who], it, ip, LOCAL) == expected


def test_admin_can_manage_disabled_item(db):
    it = item(status="disabled")
    upsert_item(db, "test", it)
    assert evaluate(db, PRINCIPALS["admin"], it, LAN, LOCAL, purpose="manage").allowed


def test_screen_is_never_admin():
    assert not PRINCIPALS["garage_tablet"].is_admin


@pytest.mark.parametrize(("who", "overrides", "assigned", "ip", "expected"), CASES)
def test_token_never_exceeds_owner(db, who, overrides, assigned, ip, expected):
    p = PRINCIPALS[who]
    if p.kind != "user":
        pytest.skip("tokens belong to users")
    it = item(**overrides)
    upsert_item(db, "test", it)
    set_assignments(db, "test", it.id, assigned)
    assert evaluate(db, token_of(p), it, ip, LOCAL) == evaluate(db, p, it, ip, LOCAL)


def test_upsert_is_audited_with_old_and_new(db):
    upsert_item(db, "user:a", item())
    upsert_item(db, "user:a", item(visibility="show"))
    rows = db.execute("SELECT action, old, new FROM audit ORDER BY id").fetchall()
    assert [r["action"] for r in rows] == ["item.create", "item.update"]
    assert '"restrict"' in rows[1]["old"] and '"show"' in rows[1]["new"]


def test_seed_builtins_idempotent_and_assigned(db):
    seed_builtins(db)
    set_assignments(db, "user:a", "section:scripts", [("role", "operator"), ("user", "sam")])
    seed_builtins(db)
    assert ("role", "operator") in get_assignments(db, "section:scripts")
    assert ("user", "sam") in get_assignments(db, "section:scripts")  # admin change kept
    assert get_assignments(db, "dashboard:home") == [("role", "household")]
    assert get_assignments(db, "section:users") == []
    home = get_item(db, "dashboard:home")
    assert home is not None and home.builtin and home.visibility == "restrict" and home.others_see == "none"
