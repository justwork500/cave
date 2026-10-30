from datetime import timedelta

import pytest

from cave.config.yamlfile import ConfigError
from cave.scripts.header import FILE_NAME, check_args, language_of, parse_header

PS1 = """\
<#
cave:
  name: Stop lab hosts
  target: sandbox
  timeout: 5m
  params:
    GraceSeconds: { type: int, default: 60, min: 0, max: 600 }
  secrets: [PROXMOX_TOKEN]
  sample: { status: "3 hosts stopped", stopped: 3 }
#>
param([int]$GraceSeconds = 60)
@{ status = "3 hosts stopped"; stopped = 3 } | ConvertTo-Json -Compress
"""

PY = """\
#!/usr/bin/env python3
# cave:
#   name: Check NAS backup age
#   timeout: 2m
#   params:
#     max_hours: { type: int, default: 26 }
import json
print(json.dumps({"status": "ok"}))
"""

SH = """\
#!/usr/bin/env bash
# cave:
#   name: Disk space report
#   target: sandbox
#   timeout: 1m
#   params:
#     warn_pct: { type: int, default: 85 }
echo '{"status":"ok"}'
"""


def test_powershell_header():
    h = parse_header("Stop-LabHosts.ps1", PS1)
    assert h.name == "Stop lab hosts" and h.timeout == timedelta(minutes=5)
    assert h.params["GraceSeconds"].max == 600 and h.secrets == ["PROXMOX_TOKEN"]
    assert h.sample == {"status": "3 hosts stopped", "stopped": 3}


def test_python_header_with_shebang():
    h = parse_header("nas.py", PY)
    assert h.name == "Check NAS backup age" and h.params["max_hours"].default == 26 and h.target == "sandbox"


def test_bash_header():
    h = parse_header("disk-report.sh", SH)
    assert h.timeout == timedelta(minutes=1) and h.secrets == []


def test_default_timeout_is_60s():
    assert parse_header("a.sh", "# cave:\n#   name: A\necho '{}'\n").timeout == timedelta(seconds=60)


def test_missing_header_error_has_line():
    with pytest.raises(ConfigError) as e:
        parse_header("x.py", "print('{}')\n")
    assert e.value.file == "x.py" and "cave:" in e.value.reason


def test_unknown_key_error_line_is_file_line():
    text = "<#\ncave:\n  name: X\n  colour: red\n#>\n"
    with pytest.raises(ConfigError) as e:
        parse_header("x.ps1", text)
    assert e.value.line == 4 and "colour" in e.value.path


def test_unknown_key_line_in_python():
    with pytest.raises(ConfigError) as e:
        parse_header("x.py", "#!/usr/bin/env python3\n# cave:\n#   name: X\n#   colour: red\n")
    assert e.value.line == 4


@pytest.mark.parametrize("target", ["ssh:nas01", "cave-host"])
def test_ssh_and_cave_host_targets_refused(target):
    with pytest.raises(ConfigError, match="only target: sandbox"):
        parse_header("x.sh", f"# cave:\n#   name: X\n#   target: {target}\n")


def test_timeout_capped_at_one_hour():
    with pytest.raises(ConfigError):
        parse_header("x.sh", "# cave:\n#   name: X\n#   timeout: 2h\n")
    assert parse_header("x.sh", "# cave:\n#   name: X\n#   timeout: 1h\n").timeout == timedelta(hours=1)


def test_sample_block():
    assert parse_header("x.sh", "# cave:\n#   name: X\n#   sample: { ok: true }\n").sample == {"ok": True}


@pytest.mark.parametrize("name", ["a.ps1", "Stop-LabHosts.ps1", "x_y.z.py", "r.sh"])
def test_file_names_ok(name):
    assert FILE_NAME.fullmatch(name)


@pytest.mark.parametrize("name", ["../x.sh", "a/b.py", "x.exe", "..sh", "a..b.py", "x\\y.sh", "", "x" * 70 + ".sh"])
def test_file_names_refused(name):
    assert not FILE_NAME.fullmatch(name)


def test_language_of():
    assert [language_of(n) for n in ("a.ps1", "a.py", "a.sh")] == ["powershell", "python", "bash"]


HEADER = parse_header("x.sh", """\
# cave:
#   name: X
#   params:
#     n: { type: int, default: 5, min: 0, max: 10 }
#     ratio: { type: float, default: 0.5 }
#     mode: { type: str, choices: [fast, slow] }
#     dry: { type: bool, default: false }
""")


@pytest.mark.parametrize(("args", "expected"), [
    ({"mode": "fast"}, {"n": 5, "ratio": 0.5, "mode": "fast", "dry": False}),
    ({"n": "7", "mode": "slow", "dry": "true"}, {"n": 7, "ratio": 0.5, "mode": "slow", "dry": True}),
    ({"n": 0, "ratio": 2, "mode": "fast", "dry": True}, {"n": 0, "ratio": 2.0, "mode": "fast", "dry": True}),
])
def test_check_args_types_defaults(args, expected):
    assert check_args(HEADER, args) == expected


@pytest.mark.parametrize("args", [
    {"mode": "fast", "n": 11}, {"mode": "fast", "n": -1}, {"mode": "medium"}, {"mode": "fast", "n": "lots"},
    {"mode": "fast", "dry": "maybe"}, {"mode": "x" * 5000},
])
def test_check_args_bounds_and_choices(args):
    with pytest.raises(ValueError):
        check_args(HEADER, args)


def test_check_args_unknown_and_missing():
    with pytest.raises(ValueError, match="unknown parameter: extra"):
        check_args(HEADER, {"mode": "fast", "extra": 1})
    with pytest.raises(ValueError, match="mode"):
        check_args(HEADER, {})
