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
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from cave.scripts.header import Language

# a statement, not an inline conditional, so type checkers on Linux don't see the Windows-only name
if sys.platform == "win32":
    _NEW_PROCESS_GROUP = subprocess.CREATE_NEW_PROCESS_GROUP
else:
    _NEW_PROCESS_GROUP = 0

MAX_OUTPUT = 1024 * 1024
LOG_LINES = 200
MASK = "•••"
TRUNCATED = "[output truncated]"
T = TypeVar("T")
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
        return {mask(k) if isinstance(k, str) else k: mask_value(v, mask) for k, v in value.items()}
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
    """Kill the script and everything it started. On Linux this works after it exited too: the session lives on
    while any of its processes do."""
    if sys.platform == "win32":
        if proc.returncode is None:
            # shortcut: Windows kill uses taskkill and loses the tree once the parent exits; Debian is the target
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, check=False)
        return
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(proc.pid, signal.SIGKILL)


def sweep(uid: int, proc: Path = Path("/proc"), kill: Callable[[int], None] | None = None) -> None:
    """Kill every process owned by the script uid, including ones that escaped into a session of their own."""
    if not proc.is_dir():
        return
    kill = kill or (lambda pid: os.kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM)))
    for entry in proc.iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            status = (entry / "status").read_text(encoding="utf-8")
        except OSError:
            continue
        uids = next((line.split()[1:] for line in status.splitlines() if line.startswith("Uid:")), [])
        if uids and int(uids[0]) == uid:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                kill(int(entry.name))


class RunGate:
    """Runs share the script uid, and a process can read the environment of another with the same uid. So a run
    with secrets never overlaps another run, and leftover script processes are swept before and after it."""

    def __init__(self, sweep_uid: int | None = None) -> None:
        self.sweep_uid = sweep_uid
        self._cond = asyncio.Condition()
        self._shared = 0
        self._exclusive = False

    def _sweep(self) -> None:
        if self.sweep_uid is not None:
            sweep(self.sweep_uid)

    async def run(self, work: Awaitable[T], exclusive: bool) -> T:
        async with self._cond:
            await self._cond.wait_for(lambda: not self._exclusive and (not exclusive or self._shared == 0))
            if exclusive:
                self._exclusive = True
                self._sweep()
            else:
                self._shared += 1
        try:
            return await work
        finally:
            async with self._cond:
                if exclusive:
                    self._exclusive = False
                else:
                    self._shared -= 1
                if self._shared == 0:
                    self._sweep()
                self._cond.notify_all()


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
    run_as: tuple[int, int] | None = None,
) -> RunResult:
    mask = masker(secrets)
    start = time.monotonic()
    argv = _argv(language, path, params)
    if argv is None:
        return RunResult(None, False, 0, None, [], f"{INTERPRETERS[language]} isn't installed on the script runner.")
    workdir = tempfile.mkdtemp(prefix="cave-run-", dir=workdir_parent)
    if run_as is not None:
        os.chown(workdir, *run_as)  # type: ignore[attr-defined,unused-ignore]
    out = _Output(mask)
    extra: dict[str, Any] = {"user": run_as[0], "group": run_as[1], "extra_groups": []} if run_as else {}
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
            creationflags=_NEW_PROCESS_GROUP,
            limit=1024 * 1024,
            **extra,
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
        except asyncio.CancelledError:  # the run was cancelled: nothing it started may live on
            _kill_tree(proc)
            raise
        _kill_tree(proc)  # a normal exit too: leftovers could read later runs' secrets
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
