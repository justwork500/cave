"""Every API call the console makes must exist on the server. The console's own tests mock the API by path, so
a wrong path passes there as long as the mock is wrong too; this checks the real routes (it once caught the whole
System page calling /networks instead of /system/networks)."""

import re
from pathlib import Path

from cave.api.app import create_app
from cave.settings import Settings

CONSOLE = Path(__file__).resolve().parents[2] / "console" / "src"
CALL = re.compile(r"api\.(get|post|put|patch|del)(?:<[^>]*>)?\(\s*[`\"]([^`\"]+)[`\"]")
METHOD = {"get": "GET", "post": "POST", "put": "PUT", "patch": "PATCH", "del": "DELETE"}
# literal paths only: a path built from variables (`/${kinds}/…`) is checked by the code that builds it
GENERIC = re.compile(r"^/api/v1/\{kinds\}")


def console_calls() -> list[tuple[str, str, str]]:
    out = []
    for f in sorted(CONSOLE.rglob("*.ts*")):
        if ".test." in f.name:
            continue
        for m in CALL.finditer(f.read_text(encoding="utf-8")):
            raw = m[2].split("?")[0]
            if raw.startswith("/${") or raw.count("${") != raw.count("}"):
                continue  # dynamic first segment or a split template: not a literal path
            out.append((METHOD[m[1]], "/api/v1" + re.sub(r"\$\{[^}]*\}", "x", raw), f.name))
    return out


def test_every_console_call_has_a_real_route(tmp_path):
    app = create_app(Settings(db_path=tmp_path / "c.db", config_dir=tmp_path))
    routes = [(m.upper(), p) for p, ops in app.openapi()["paths"].items() for m in ops]
    app.state.db.close()
    calls = console_calls()
    assert len(calls) > 50  # the scan itself works

    def served(method: str, path: str) -> bool:
        for m, p in routes:
            if m == method and re.fullmatch(re.sub(r"\{[^}]+\}", "[^/]+", p), path):
                # /{kinds} answers any single word, then refuses unknown ones: only real kinds count
                if not GENERIC.match(p) or path.split("/")[3] in ("automations", "sequences", "dashboards"):
                    return True
        return False

    missing = [f"{m} {p} ({f})" for m, p, f in calls if not served(m, p)]
    assert missing == []
