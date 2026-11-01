"""A fresh install starts with a Home dashboard file to edit; one an Admin deleted stays deleted."""

from cave.api.app import create_app
from cave.settings import Settings


def _start(tmp_path):
    app = create_app(Settings(db_path=tmp_path / "c.db", config_dir=tmp_path / "config"))
    app.state.db.close()
    return tmp_path / "config" / "dashboards" / "home.yaml"


def test_fresh_install_gets_an_editable_home_dashboard(tmp_path):
    home = _start(tmp_path)
    assert home.exists()
    assert "title: Home" in home.read_text(encoding="utf-8")


def test_a_deleted_home_dashboard_is_not_recreated(tmp_path):
    _start(tmp_path).unlink()
    assert not _start(tmp_path).exists()
