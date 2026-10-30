"""The script runner's HTTP API. It runs only scripts directly inside its read-only /scripts folder."""

import dataclasses
import hmac
import shutil
import sys
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from cave.runner.execute import execute
from cave.scripts.header import FILE_NAME, language_of


class RunRequest(BaseModel):
    script: str = Field(max_length=100)
    params: dict[str, Any] = {}
    secrets: dict[str, str] = {}
    timeout: float = Field(gt=0, le=3600)


def create_runner_app(scripts_dir: Path, token: str) -> FastAPI:
    app = FastAPI(title="CAVE script runner", docs_url=None, redoc_url=None, openapi_url=None)
    root = scripts_dir.resolve()

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
        result = await execute(path, language_of(body.script), body.params, body.secrets, body.timeout)
        return dataclasses.asdict(result)

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
