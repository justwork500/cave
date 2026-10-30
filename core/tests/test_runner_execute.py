import asyncio
import os
import shutil
import time

import pytest

from cave.runner.execute import MASK, execute

needs_pwsh = pytest.mark.skipif(shutil.which("pwsh") is None, reason="PowerShell 7 isn't installed")
needs_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="bash isn't installed")

PY_ECHO = """\
import json, os, sys
data = json.load(sys.stdin)
print("working...")
print(json.dumps({"stdin": data, "env": os.environ.get("CAVE_PARAM_NAME")}))
"""

SH_ECHO = """\
read -r stdin
echo "working..."
printf '{"env":"%s","stdin":%s}\\n' "$CAVE_PARAM_NAME" "$stdin"
"""

PS_ECHO = """\
param([string]$Name)
$stdin = [Console]::In.ReadToEnd()
Write-Output "working..."
@{ named = $Name; env = $env:CAVE_PARAM_NAME; stdin = ($stdin | ConvertFrom-Json) } | ConvertTo-Json -Compress
"""


def write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8", newline="\n")
    return p


def run(path, language, params=None, secrets=None, timeout=20.0):
    return asyncio.run(execute(path, language, params or {}, secrets or {}, timeout))


def test_python_params_env_stdin_and_result(tmp_path):
    r = run(write(tmp_path, "a.py", PY_ECHO), "python", {"name": "kitchen"})
    assert r.exit_code == 0 and r.error is None, r.log
    assert r.result == {"stdin": {"name": "kitchen"}, "env": "kitchen"}
    assert "working..." in r.log


@needs_bash
def test_bash_params_and_result(tmp_path):
    r = run(write(tmp_path, "a.sh", SH_ECHO), "bash", {"name": "kitchen"})
    assert r.error is None, r.log
    assert r.result == {"env": "kitchen", "stdin": {"name": "kitchen"}}


@needs_pwsh
def test_powershell_named_params_and_result(tmp_path):
    r = run(write(tmp_path, "a.ps1", PS_ECHO), "powershell", {"Name": "kitchen"})
    assert r.error is None, r.log
    assert r.result == {"named": "kitchen", "env": "kitchen", "stdin": {"Name": "kitchen"}}


NASTY = ['"; rm -rf ~', "$(id)", "`id`", "-Command evil", "-EncodedCommand ZQBjAGgAbwA=", "a' ; echo pwned"]


@pytest.mark.parametrize("value", NASTY)
def test_parameter_injection_is_data_python(tmp_path, value):  # Review Focus 2
    r = run(write(tmp_path, "a.py", PY_ECHO), "python", {"name": value})
    assert r.result == {"stdin": {"name": value}, "env": value}


@needs_bash
@pytest.mark.parametrize("value", NASTY)
def test_parameter_injection_is_data_bash(tmp_path, value):  # Review Focus 2
    script = 'read -r _\nprintf \'%s\\n\' "$CAVE_PARAM_NAME" >&2\nprintf \'{"ok":true}\\n\'\n'
    r = run(write(tmp_path, "a.sh", script), "bash", {"name": value})
    assert r.error is None and value in r.log and "pwned" not in "\n".join(r.log).replace(value, "")


@needs_pwsh
@pytest.mark.parametrize("value", NASTY)
def test_parameter_injection_is_data_powershell(tmp_path, value):  # Review Focus 2
    r = run(write(tmp_path, "a.ps1", PS_ECHO), "powershell", {"Name": value})
    assert r.error is None, r.log
    assert r.result["named"] == value and r.result["env"] == value


def test_secret_masked_in_log_and_error(tmp_path):  # Review Focus 3
    script = ("import os\nprint('token is', os.environ['API_TOKEN'])\n"
              "raise SystemExit('failed with ' + os.environ['API_TOKEN'])\n")
    r = run(write(tmp_path, "a.py", script), "python", secrets={"API_TOKEN": "hunter2-secret"})
    text = "\n".join(r.log) + str(r.error) + str(r.result)
    assert "hunter2-secret" not in text and MASK in text
    assert r.exit_code != 0


def test_secret_masked_in_result(tmp_path):
    script = "import os, json\nprint(json.dumps({'leak': os.environ['API_TOKEN']}))\n"
    r = run(write(tmp_path, "a.py", script), "python", secrets={"API_TOKEN": "hunter2-secret"})
    assert r.result == {"leak": MASK}


def test_non_json_last_line_fails(tmp_path):
    r = run(write(tmp_path, "a.py", "print('done')\n"), "python")
    assert r.exit_code == 0 and r.result is None and "JSON object" in r.error


def test_nonzero_exit_fails_with_tail(tmp_path):
    r = run(write(tmp_path, "a.py", "print('step 1')\nimport sys\nsys.exit(3)\n"), "python")
    assert r.exit_code == 3 and "code 3" in r.error and "step 1" in r.log


def test_timeout_kills_child_too(tmp_path):  # Review Focus 4
    marker = tmp_path / "marker.txt"
    script = (
        "import subprocess, sys, time\n"
        f"subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(2); open(\"{marker.as_posix()}\", \"w\").write(\"x\")'])\n"
        "time.sleep(30)\n"
    )
    start = time.monotonic()
    r = run(write(tmp_path, "a.py", script), "python", timeout=1)
    assert r.timed_out and "stopped" in r.error and time.monotonic() - start < 5
    time.sleep(2.5)
    assert not marker.exists()


def test_huge_output_capped(tmp_path):  # Review Focus 4
    script = "import sys, json\nfor _ in range(500):\n    sys.stdout.write('x' * 100_000 + '\\n')\nprint(json.dumps({'ok': 1}))\n"
    start = time.monotonic()
    r = run(write(tmp_path, "a.py", script), "python", timeout=30)
    assert time.monotonic() - start < 20
    assert sum(len(line) for line in r.log) < 1_100_000 and "[output truncated]" in r.log
    assert r.result == {"ok": 1}  # the final line still counts


def test_env_is_minimal(tmp_path, monkeypatch):
    monkeypatch.setenv("CAVE_TEST_LEAK", "leaked")
    script = "import os, json\nprint(json.dumps({'leak': os.environ.get('CAVE_TEST_LEAK'), 'path': bool(os.environ.get('PATH'))}))\n"
    r = run(write(tmp_path, "a.py", script), "python")
    assert r.result == {"leak": None, "path": True}


def test_workdir_removed(tmp_path):
    script = "import os, json\nprint(json.dumps({'cwd': os.getcwd()}))\n"
    r = run(write(tmp_path, "a.py", script), "python")
    assert not os.path.exists(r.result["cwd"])


def test_missing_interpreter_reported(tmp_path, monkeypatch):
    monkeypatch.setattr("cave.runner.execute.shutil.which", lambda name: None)
    r = run(write(tmp_path, "a.sh", "echo '{}'\n"), "bash")
    assert r.exit_code is None and "isn't installed" in r.error

