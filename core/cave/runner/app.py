"""The script runner's HTTP API. It runs only scripts directly inside its read-only /scripts folder."""

import asyncio
import dataclasses
import hmac
import shutil
import sys
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, Field

from cave.runner.execute import RunGate, RunResult, execute
from cave.scripts.header import FILE_NAME, language_of


class RunRequest(BaseModel):
    script: str = Field(max_length=100)
    params: dict[str, Any] = {}
    secrets: dict[str, str] = {}
    timeout: float = Field(gt=0, le=3600)
    run_id: str | None = Field(default=None, max_length=64)


def create_runner_app(scripts_dir: Path, token: str, run_as: tuple[int, int] | None = None) -> FastAPI:
    """run_as: the uid/gid scripts run as, never the runner's own (Linux). Its processes are swept around secret runs."""
    app = FastAPI(title="CAVE script runner", docs_url=None, redoc_url=None, openapi_url=None)
    root = scripts_dir.resolve()
    gate = RunGate(sweep_uid=run_as[0] if run_as else None)
    running: dict[str, asyncio.Task[RunResult]] = {}

    def authorized(request: Request) -> None:
        scheme, _, given = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(given.encode(), token.encode()):
            raise HTTPException(401, "Unauthorized.")

    Auth = Annotated[None, Depends(authorized)]

    @app.post("/run")
    async def run(body: RunRequest, _: Auth) -> dict[str, Any]:
        if not FILE_NAME.fullmatch(body.script):
            raise HTTPException(400, "Not a script name.")
        path = (root / body.script).resolve()
        if path.parent != root:  # also catches a symlink pointing outside the folder
            raise HTTPException(400, "Scripts must be inside the scripts folder.")
        if not path.is_file():
            raise HTTPException(404, "No such script.")
        work = execute(path, language_of(body.script), body.params, body.secrets, body.timeout, run_as=run_as)
        task = asyncio.create_task(gate.run(work, exclusive=bool(body.secrets)))
        if body.run_id:
            running[body.run_id] = task
        try:
            result = await task
        except asyncio.CancelledError:
            if not task.cancelled():
                raise  # the runner itself is shutting down
            result = RunResult(None, False, 0, None, [], "The run was cancelled.")
        finally:
            if body.run_id:
                running.pop(body.run_id, None)
        return dataclasses.asdict(result)

    @app.post("/cancel/{run_id}", status_code=204)
    async def cancel(run_id: str, _: Auth) -> Response:
        task = running.get(run_id)
        if task is None:
            raise HTTPException(404, "No such run.")
        task.cancel()
        return Response(status_code=204)

    @app.get("/health")
    def health(_: Auth) -> dict[str, Any]:
        return {
            "status": "ok",
            "interpreters": {
                "pwsh": shutil.which("pwsh") is not None,
                "python3": bool(sys.executable),
                "bash": shutil.which("bash") is not None,
            },
        }

    return app
