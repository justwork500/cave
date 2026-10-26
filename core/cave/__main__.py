"""`python -m cave serve` — run CAVE over HTTPS. There is no plain-HTTP listener."""

import argparse
import socket
from pathlib import Path

import uvicorn

from cave import tls
from cave.access import netconfig
from cave.api.app import create_app
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
    args = parser.parse_args(argv)

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
    print(f"CAVE is running at https://{ip or 'localhost'}:{args.port}")
    print(f"Certificate fingerprint (SHA-256): {tls.fingerprint(cert)}")
    uvicorn.run(app, host=args.host, port=args.port, ssl_certfile=str(cert), ssl_keyfile=str(key))


if __name__ == "__main__":
    main()
