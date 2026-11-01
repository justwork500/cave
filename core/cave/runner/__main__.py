"""`python -m cave.runner` — the script runner sidecar. Reachable only on the internal Compose network."""

import argparse
import os
import sys
from pathlib import Path

import uvicorn

from cave.runner.app import create_runner_app

MIN_TOKEN = 32


def _token(token_file: Path | None) -> str:
    # a file (a Compose secret), not an environment variable: scripts can read environments, not root's files
    path = token_file or (Path(p) if (p := os.environ.get("CAVE_RUNNER_TOKEN_FILE")) else None)
    if path is not None:
        return path.read_text(encoding="utf-8").strip()
    return os.environ.get("CAVE_RUNNER_TOKEN", "")  # development only


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="cave.runner")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8099)
    parser.add_argument("--scripts", type=Path, default=Path("/scripts"))
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--script-uid", type=int, help="uid (and gid) scripts run as; never the runner's own")
    args = parser.parse_args(argv)
    token = _token(args.token_file)
    if len(token) < MIN_TOKEN:
        sys.exit(f"The runner token must be at least {MIN_TOKEN} characters (--token-file or CAVE_RUNNER_TOKEN_FILE).")
    run_as = (args.script_uid, args.script_uid) if args.script_uid is not None else None
    # asyncio, not uvloop (which uvicorn[standard] would pick): uvloop's subprocess_exec refuses user= and group=
    uvicorn.run(create_runner_app(args.scripts, token, run_as), host=args.host, port=args.port, loop="asyncio")


if __name__ == "__main__":
    main()
