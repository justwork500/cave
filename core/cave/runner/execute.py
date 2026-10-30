"""Run one script under the cave contract. This is the only code that starts a script process.

Params go in as environment variables, JSON on stdin and (PowerShell) `-Name:value` arguments, never through a
shell. The last stdout line is the JSON result. Secrets are masked before any output is kept.
"""

import asyncio
import contextlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cave.scripts.header import Language

MAX_OUTPUT = 1024 * 1024
LOG_LINES = 200
MASK = "•••"
TRUNCATED = "[output truncated]"
INTERPRETERS: dict[Language, str] = {"powershell": "pwsh", "python": "python3", "bash": "bash"}


@dataclass(frozen=True)
class RunResult:
    exit_code: int | None
    timed_out: bool
    duration_ms: int
    result: dict[str, Any] | None
    log: list[str]
    error: str | None


def masker(secrets: dict[str, str]) -> Any:
    values = sorted((v for v in secrets.values() if len(v) >= 4), key=len, reverse=True)

    def mask(text: str) -> str:
        for v in values:
            text = text.replace(v, MASK)
        return text

    return mask


def mask_value(value: Any, mask: Any) -> Any:
    if isinstance(value, str):
        return mask(value)
    if isinstance(value, dict):
        return {k: mask_value(v, mask) for k, v in value.items()}
    if isinstance(value, list):
        return [mask_value(v, mask) for v in value]
    return value


def _env_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return value if isinstance(value, str) else json.dumps(value)


def _argv(language: Language, path: Path, params: dict[str, Any]) -> list[str] | None:
    if language == "python":
        return [sys.executable or "python3", "-I", str(path)]
    exe = shutil.which(INTERPRETERS[language])
    if exe is None:
        return None
    if language == "bash":
        return [exe, str(path)]
    # -Name:value binds the value even when it starts with '-', so it can never become an option
    named = [f"-{k}:{('$true' if v else '$false') if isinstance(v, bool) else _env_value(v)}" for k, v in params.items()]
    return [exe, "-NoLogo", "-NoProfile", "-NonInteractive", "-File", str(path), *named]


def _env(workdir: str, params: dict[str, Any], secrets: dict[str, str]) -> dict[str, str]:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": workdir, "LANG": "C.UTF-8", "TMPDIR": workdir}
    if sys.platform == "win32":  # interpreters can't start on Windows without these
        for key in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP"):
            env[key] = workdir if key in ("TEMP", "TMP") else os.environ.get(key, "")
    env.update({f"CAVE_PARAM_{k.upper()}": _env_value(v) for k, v in params.items()})
    env.update(secrets)
    return env


def _kill_tree(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    if sys.platform == "win32":
        # shortcut: Windows kill uses taskkill; Debian (killpg below) is the target
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, check=False)
    else:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)


class _Output:
    def __init__(self, mask: Any) -> None:
        self.mask = mask
        self.lines: list[str] = []
        self.size = 0
        self.truncated = False
        self.last_stdout = ""

    async def read(self, stream: asyncio.StreamReader, is_stdout: bool) -> None:
        while True:
            try:
                raw = await stream.readline()
            except ValueError:  # a single line over the stream limit: keep draining in chunks
                raw = await stream.read(65536)
            if not raw:
                return
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            if is_stdout and line.strip():
                self.last_stdout = line
            if self.size + len(line) > MAX_OUTPUT:
                if not self.truncated:
                    self.truncated = True
                    self.lines.append(TRUNCATED)
                continue  # keep draining so the script never blocks on a full pipe
            self.size += len(line)
            self.lines.append(self.mask(line))


async def execute(
    path: Path,
    language: Language,
    params: dict[str, Any],
    secrets: dict[str, str],
    timeout: float,
    workdir_parent: Path | None = None,
) -> RunResult:
    mask = masker(secrets)
    start = time.monotonic()
    argv = _argv(language, path, params)
    if argv is None:
        return RunResult(None, False, 0, None, [], f"{INTERPRETERS[language]} isn't installed on the script runner.")
    workdir = tempfile.mkdtemp(prefix="cave-run-", dir=workdir_parent)
    out = _Output(mask)
    timed_out = False
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workdir,
            env=_env(workdir, params, secrets),
            start_new_session=sys.platform != "win32",
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
            limit=1024 * 1024,
        )
        assert proc.stdin and proc.stdout and proc.stderr
        with contextlib.suppress(BrokenPipeError, ConnectionResetError):
            proc.stdin.write(json.dumps(params).encode())
            await proc.stdin.drain()
            proc.stdin.close()
        readers = asyncio.gather(out.read(proc.stdout, True), out.read(proc.stderr, False))
        try:
            await asyncio.wait_for(proc.wait(), timeout)
        except TimeoutError:
            timed_out = True
            _kill_tree(proc)
            await proc.wait()
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(readers, 5)  # pipes close once every process in the tree is gone
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    duration = int((time.monotonic() - start) * 1000)
    log = out.lines[-LOG_LINES:]
    if timed_out:
        return RunResult(proc.returncode, True, duration, None, log,
                         f"The script took longer than {timeout:.0f} s and was stopped.")
    if proc.returncode != 0:
        return RunResult(proc.returncode, False, duration, None, log, f"The script exited with code {proc.returncode}.")
    try:
        result = json.loads(out.last_stdout)
    except ValueError:
        result = None
    if not isinstance(result, dict):
        return RunResult(0, False, duration, None, log, "The script must end by printing one JSON object.")
    return RunResult(0, False, duration, mask_value(result, mask), log, None)
