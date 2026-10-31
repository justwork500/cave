"""`python -m cave serve` runs CAVE over HTTPS (there is no plain-HTTP listener); `schemas` writes JSON Schemas."""

import argparse
import asyncio
import json
import socket
import sys
from pathlib import Path

import uvicorn

from cave import tls
from cave.access import netconfig
from cave.api.app import create_app
from cave.api.setup import ensure_setup_code
from cave.config.models import schema_files
from cave.settings import Settings


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="cave")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="Run CAVE over HTTPS")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8443)
    serve.add_argument("--data", type=Path, default=Path("data"))
    serve.add_argument("--config", type=Path, default=Path("config"))
    serve.add_argument("--cert", type=Path, help="Your own certificate (PEM). Use with --key.")
    serve.add_argument("--key", type=Path, help="Private key for --cert (PEM).")
    schemas = sub.add_parser("schemas", help="Write JSON Schemas for the YAML config files")
    schemas.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[2] / "schemas")
    args = parser.parse_args(argv)

    if args.command == "schemas":
        args.out.mkdir(parents=True, exist_ok=True)
        for name, schema in schema_files().items():
            text = json.dumps(schema, indent=2, sort_keys=True) + "\n"
            (args.out / name).write_text(text, encoding="utf-8", newline="\n")
            print(f"wrote {args.out / name}")
        return

    if bool(args.cert) != bool(args.key):
        parser.error("--cert and --key go together")
    args.data.mkdir(parents=True, exist_ok=True)
    ip = netconfig.host_ipv4()
    if args.cert:
        cert, key = args.cert, args.key
    else:
        cert, key = tls.ensure_certificate(
            args.data / "tls", [socket.gethostname(), "localhost"], [a for a in (ip, "127.0.0.1") if a]
        )
    app = create_app(Settings(db_path=args.data / "cave.db", config_dir=args.config))
    app.state.cert_path = cert
    code = ensure_setup_code(app.state.db)
    if code:
        print(f"CAVE isn't set up yet. Open it in a browser and use this one-time setup code: {code}")
    print(f"CAVE is running at https://{ip or 'localhost'}:{args.port}")
    print(f"Certificate fingerprint (SHA-256): {tls.fingerprint(cert)}")
    config = uvicorn.Config(app, host=args.host, port=args.port, ssl_certfile=str(cert), ssl_keyfile=str(key))
    server = uvicorn.Server(config)
    if sys.platform == "win32":
        # aiomqtt needs a selector loop; Windows defaults to Proactor.
        # shortcut: Windows is a dev convenience; Debian is the target
        asyncio.run(server.serve(), loop_factory=asyncio.SelectorEventLoop)
    else:
        server.run()


if __name__ == "__main__":
    main()
