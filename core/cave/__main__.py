"""`python -m cave serve` runs CAVE over HTTPS (there is no plain-HTTP listener); `schemas` writes JSON Schemas;
`health` checks a running CAVE on this machine (the container health check)."""

import argparse
import asyncio
import json
import ssl
import sys
import urllib.request
from pathlib import Path

import uvicorn

from cave import tls
from cave.api.app import create_app
from cave.api.setup import ensure_setup_code
from cave.config.models import schema_files
from cave.envconfig import cert_names, cert_paths, settings_from_env


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
    health = sub.add_parser("health", help="Exit 0 if CAVE on this machine answers its health check")
    health.add_argument("--port", type=int, default=8443)
    args = parser.parse_args(argv)

    if args.command == "health":
        sys.exit(0 if _healthy(args.port) else 1)

    if args.command == "schemas":
        args.out.mkdir(parents=True, exist_ok=True)
        for name, schema in schema_files().items():
            text = json.dumps(schema, indent=2, sort_keys=True) + "\n"
            (args.out / name).write_text(text, encoding="utf-8", newline="\n")
            print(f"wrote {args.out / name}")
        return

    own = cert_paths(args.cert, args.key)
    args.data.mkdir(parents=True, exist_ok=True)
    names, ips = cert_names()
    cert, key = own or tls.ensure_certificate(args.data / "tls", names, ips)
    app = create_app(settings_from_env(args.data, args.config))
    app.state.cert_path = cert
    code = ensure_setup_code(app.state.db)
    if code:
        print(f"CAVE isn't set up yet. Open it in a browser and use this one-time setup code: {code}")
    print(f"CAVE is running at https://{ips[0] if ips[0] != '127.0.0.1' else 'localhost'}:{args.port}")
    print(f"Certificate fingerprint (SHA-256): {tls.fingerprint(cert)}")
    config = uvicorn.Config(app, host=args.host, port=args.port, ssl_certfile=str(cert), ssl_keyfile=str(key))
    server = uvicorn.Server(config)
    if sys.platform == "win32":
        # aiomqtt needs a selector loop; Windows defaults to Proactor.
        # shortcut: Windows is a dev convenience; Debian is the target
        asyncio.run(server.serve(), loop_factory=asyncio.SelectorEventLoop)
    else:
        server.run()


def _healthy(port: int) -> bool:
    # loopback only, and the certificate is CAVE's own, so not checking it here proves nothing away
    context = ssl.create_default_context()
    context.check_hostname, context.verify_mode = False, ssl.CERT_NONE
    try:
        with urllib.request.urlopen(f"https://127.0.0.1:{port}/api/v1/health", timeout=5, context=context) as r:
            return bool(r.status == 200 and json.load(r) == {"status": "ok"})
    except (OSError, ValueError):  # URLError, timeouts and refused connections are OSErrors
        return False


if __name__ == "__main__":
    main()
