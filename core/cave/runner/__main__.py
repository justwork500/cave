"""`python -m cave.runner` — the script runner sidecar. Reachable only on the internal Compose network."""

import argparse
import os
import sys
from pathlib import Path

import uvicorn

from cave.runner.app import create_runner_app

MIN_TOKEN = 32


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="cave.runner")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8099)
    parser.add_argument("--scripts", type=Path, default=Path("/scripts"))
    args = parser.parse_args(argv)
    token = os.environ.get("CAVE_RUNNER_TOKEN", "")
    if len(token) < MIN_TOKEN:
        sys.exit(f"CAVE_RUNNER_TOKEN must be set to at least {MIN_TOKEN} characters.")
    uvicorn.run(create_runner_app(args.scripts, token), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
