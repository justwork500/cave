import pytest

from cave.controls import check_command

SOURCES = {"sources": ["HDMI 1", "HDMI 2"]}


def test_media_commands_accepted() -> None:
    for cmd in ("turn_on", "turn_off", "toggle", "play", "pause", "play_pause"):
        assert check_command("media_player", cmd, {}, {}) == {}
    assert check_command("media_player", "volume_set", {"level": "35"}, {}) == {"level": 35}
    assert check_command("media_player", "volume_mute", {"muted": True}, {}) == {"muted": True}
    assert check_command("media_player", "select_source", {"source": "HDMI 1"}, SOURCES) == {"source": "HDMI 1"}


def test_media_bad_args_refused() -> None:
    with pytest.raises(ValueError, match="0 to 100"):
        check_command("media_player", "volume_set", {"level": 101}, {})
    with pytest.raises(ValueError, match="0 to 100"):
        check_command("media_player", "volume_set", {"level": "loud"}, {})
    with pytest.raises(ValueError, match="HDMI 9"):
        check_command("media_player", "select_source", {"source": "HDMI 9"}, {"sources": ["HDMI 1"]})
    with pytest.raises(ValueError, match="can't"):
        check_command("media_player", "rewind", {}, {})
    with pytest.raises(ValueError, match="true or false"):
        check_command("media_player", "volume_mute", {"muted": "maybe"}, {})


def test_number_snaps_and_bounds() -> None:
    attrs = {"min": 0, "max": 255, "step": 5}
    assert check_command("number", "set_value", {"value": 12}, attrs) == {"value": 10}
    assert check_command("number", "set_value", {"value": "13"}, attrs) == {"value": 15}
    assert check_command("number", "set_value", {"value": 7}, {"min": 2, "max": 20, "step": 5}) == {"value": 7}
    with pytest.raises(ValueError, match="0 to 255"):
        check_command("number", "set_value", {"value": 300}, attrs)
    with pytest.raises(ValueError, match="number"):
        check_command("number", "set_value", {"value": "x"}, attrs)


def test_select_option_must_exist() -> None:
    attrs = {"options": ["Rainbow", "Fire"]}
    assert check_command("select", "select_option", {"option": "Fire"}, attrs) == {"option": "Fire"}
    with pytest.raises(ValueError, match="Ice"):
        check_command("select", "select_option", {"option": "Ice"}, attrs)


def test_other_capabilities_unchanged() -> None:
    assert check_command("switch", "turn_on", {}, {}) == {}
    assert check_command("light", "anything", {"x": 1}, {}) == {"x": 1}
