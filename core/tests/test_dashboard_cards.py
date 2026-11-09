"""Tile looks and script buttons on dashboards."""

import pytest

from cave.access.items import set_assignments
from cave.config.store import parse
from cave.config.yamlfile import ConfigError
from tests.conftest import lan_client, sign_in


def board(card: str) -> str:
    return f"""\
dashboard:
  title: Board
  views:
    - id: main
      title: Main
      sections:
        - title: One
          cards:
            - {card}
"""


TILE = "{type: tile, entity: switch.lamp, label: Lamp, icon: wind, color: blue}"
PLAIN_SH = "# cave:\n#   name: Plain\necho \'{}\'\n"
INPUT_SH = "# cave:\n#   name: Needs input\n#   params:\n#     host: {type: str}\necho \'{}\'\n"


def put(app, folder, name, text):
    d = app.state.settings.config_dir / folder
    d.mkdir(exist_ok=True)
    (d / name).write_text(text, encoding="utf-8")


def with_script(app):
    put(app, "scripts", "backup-photos.sh", PLAIN_SH)
    put(app, "dashboards", "board.yaml", board("{type: button, name: Back up, action: script.backup-photos.sh}"))
    app.state.scripts.load_all()
    app.state.config.load_all()


def admin(app, users):
    return sign_in(lan_client(app), "admin", "pw-admin-1234", users.admin_totp)


def op(app, users):
    return sign_in(lan_client(app), "op", "pw-op-1234", users.op_totp)


def cards(client):
    return client.get("/api/v1/dashboards/board/view").json()["views"][0]["sections"][0]["cards"]


def test_cards_take_a_label_icon_and_colour():
    card = parse("dashboard", "board", board(TILE)).views[0].sections[0].cards[0]
    assert (card.label, card.icon, card.color) == ("Lamp", "wind", "blue")


@pytest.mark.parametrize("extra", ["icon: rocket", "color: pink"])
def test_unknown_icon_or_colour_is_refused(extra):
    with pytest.raises(ConfigError):
        parse("dashboard", "board", board(f"{{type: tile, entity: switch.lamp, {extra}}}"))


def test_view_passes_the_new_fields_through(app, users):
    put(app, "dashboards", "board.yaml", board(TILE))
    app.state.config.load_all()
    card = cards(admin(app, users))[0]
    assert (card["label"], card["icon"], card["color"]) == ("Lamp", "wind", "blue")


def test_a_script_button_needs_a_valid_file():
    good = "{type: button, name: Go, action: script.backup-photos.sh}"
    assert parse("dashboard", "board", board(good)).views[0].sections[0].cards[0].action == "script.backup-photos.sh"
    for bad in ("script.../evil.sh", "script.a..b.sh", "script.notes.txt"):
        with pytest.raises(ConfigError):
            parse("dashboard", "board", board(f"{{type: button, name: Go, action: {bad}}}"))


def test_script_button_is_allowed_for_who_can_run_it(app, users):
    with_script(app)
    set_assignments(app.state.db, "test", "dashboard:board", [("role", "operator")])
    assert cards(admin(app, users))[0]["allowed"] is True
    assert cards(op(app, users))[0]["allowed"] is True  # through the Scripts section


def test_script_button_is_locked_for_who_cant(app, users):
    with_script(app)
    set_assignments(app.state.db, "test", "section:scripts", [("role", "admin")])
    set_assignments(app.state.db, "test", "script:backup-photos.sh", [("role", "admin")])
    set_assignments(app.state.db, "test", "dashboard:board", [("role", "operator")])
    assert cards(op(app, users))[0]["allowed"] is False


def test_saving_a_script_button_you_cant_run_is_refused(app, users):
    with_script(app)
    set_assignments(app.state.db, "test", "script:backup-photos.sh", [("role", "admin")])
    r = op(app, users).put("/api/v1/dashboards/mine?create=true", json={
        "yaml": board("{type: button, name: Go, action: script.backup-photos.sh}")})
    assert r.status_code == 403 and "backup-photos.sh" in r.json()["detail"]


def test_script_list_says_which_can_run_from_a_button(app, users):
    put(app, "scripts", "plain.sh", PLAIN_SH)
    put(app, "scripts", "input.sh", INPUT_SH)
    app.state.scripts.load_all()
    rows = {s["file"]: s["runnable"] for s in admin(app, users).get("/api/v1/scripts").json()}
    assert rows == {"plain.sh": True, "input.sh": False}


def test_script_button_follows_a_script_assignment_over_the_section(app, users):
    with_script(app)  # the operator holds the Scripts section, but this script is now assigned to Admins only
    set_assignments(app.state.db, "test", "script:backup-photos.sh", [("role", "admin")])
    set_assignments(app.state.db, "test", "dashboard:board", [("role", "operator")])
    assert [c["allowed"] for c in cards(op(app, users))] in ([], [False])
