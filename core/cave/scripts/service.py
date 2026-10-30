"""Run a script: check its parameters, hand it to the runner sidecar, mask, record and audit the result."""

import asyncio
import json
import os
import urllib.error
import urllib.request
import uuid
from collections.abc import Awaitable, Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

from cave import audit
from cave.db import Database
from cave.runner.execute import mask_value, masker
from cave.scripts.header import check_args
from cave.scripts.store import ScriptStore

RunnerPost = Callable[[str, dict[str, Any], float], Awaitable[dict[str, Any]]]
RUNNER_SLACK = 10.0  # seconds the runner gets beyond the script's own timeout before we give up
KEEP_RUNS = 100
TAIL = 20


class RunnerError(Exception):
    pass


class RunnerClient:
    """Talks to cave-script-runner over the internal network. Standard library only."""

    def __init__(self, url: str, token: str) -> None:
        self.url, self.token = url.rstrip("/"), token
        # its own pool: a long script must not tie up the event loop's default threads
        self._pool = ThreadPoolExecutor(max_workers=32, thread_name_prefix="cave-runner")

    async def post(self, path: str, body: dict[str, Any], timeout: float) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._pool, self._post, path, body, timeout + RUNNER_SLACK)

    def _post(self, path: str, body: dict[str, Any], timeout: float) -> dict[str, Any]:
        request = urllib.request.Request(
            self.url + path, data=json.dumps(body).encode(), method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
            data = json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            raise RunnerError(f"The script runner refused the request ({e.code}).") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise RunnerError(f"The script runner can't be reached: {e}") from e
        except ValueError as e:
            raise RunnerError("The script runner sent something that isn't JSON.") from e
        if not isinstance(data, dict):
            raise RunnerError("The script runner sent something unexpected.")
        return data


class ScriptService:
    def __init__(self, store: ScriptStore, db: Database, runner: RunnerPost | None,
                 environ: Mapping[str, str] = os.environ) -> None:
        self.store, self.db, self.runner, self.environ = store, db, runner, environ
        self._cancels: set[asyncio.Future[dict[str, Any]]] = set()

    def sample(self, file: str) -> dict[str, Any] | None:
        loaded = self.store.get(file)
        return loaded.header.sample if loaded else None

    async def run(self, file: str, args: Mapping[str, Any], started_by: str) -> dict[str, Any]:
        loaded = self.store.get(file)
        if loaded is None:
            raise ValueError(f"There's no script called {file!r}.")
        try:
            params = check_args(loaded.header, args)
        except ValueError as e:
            raise ValueError(f"{file}: {e}") from e
        secrets: dict[str, str] = {}
        for name in loaded.header.secrets:
            value = self.environ.get(f"CAVE_SECRET_{name}")
            if not value:
                raise ValueError(f"Secret {name} isn't set on this CAVE.")
            secrets[name] = value
        if self.runner is None:
            raise ValueError("The script runner isn't set up.")
        timeout = loaded.header.timeout.total_seconds()
        started = datetime.now(UTC).isoformat()
        run_id = uuid.uuid4().hex
        try:
            raw = await self.runner("/run", {"script": file, "params": params, "secrets": secrets,
                                             "timeout": timeout, "run_id": run_id}, timeout)
        except asyncio.CancelledError:
            # the automation was stopped or restarted: stop the script too
            cancel = asyncio.ensure_future(self.runner(f"/cancel/{run_id}", {}, 5))
            self._cancels.add(cancel)
            cancel.add_done_callback(self._cancels.discard)
            raise
        except RunnerError as e:
            raw = {"exit_code": None, "timed_out": False, "duration_ms": 0, "result": None, "log": [],
                   "error": str(e)}
        mask = masker(secrets)
        out: dict[str, Any] = mask_value(raw, mask)  # again here, in case the runner missed something
        log = [str(line) for line in out.get("log") or []][-200:]
        error, result = out.get("error"), out.get("result")
        outcome = "timed_out" if out.get("timed_out") else ("failed" if error else "finished")
        self._record(file, started_by, params, started, out, outcome, log, result)
        audit.record(self.db, started_by, "script.run", f"script:{file}", None,
                     {"outcome": outcome, "exit_code": out.get("exit_code"), "result": result})
        if error:
            raise ValueError("\n".join([str(error), *log[-TAIL:]]))
        return result if isinstance(result, dict) else {}

    def _record(self, file: str, started_by: str, params: dict[str, Any], started: str, out: dict[str, Any],
                outcome: str, log: list[str], result: Any) -> None:
        self.db.execute(
            "INSERT INTO script_runs (script, started_by, target, params, started_at, duration_ms, exit_code, "
            "outcome, log, result) VALUES (?, ?, 'sandbox', ?, ?, ?, ?, ?, ?, ?)",
            (file, started_by, json.dumps(params), started, out.get("duration_ms"), out.get("exit_code"), outcome,
             json.dumps(log), json.dumps(result)),
        )
        self.db.execute(
            "DELETE FROM script_runs WHERE script=? AND id NOT IN "
            "(SELECT id FROM script_runs WHERE script=? ORDER BY id DESC LIMIT ?)",
            (file, file, KEEP_RUNS),
        )

    def runs(self, file: str) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT id, started_by, target, params, started_at, duration_ms, exit_code, outcome, log, result "
            "FROM script_runs WHERE script=? ORDER BY id DESC", (file,)
        ).fetchall()
        return [dict(r) | {k: json.loads(r[k]) for k in ("params", "log", "result")} for r in rows]
