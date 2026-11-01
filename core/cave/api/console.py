"""Serve the built console (a single-page app) and put strict security headers on every page."""

from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

CONSOLE_DIR = Path(__file__).resolve().parent.parent / "web" / "console"
NOT_BUILT = (
    "<!doctype html><meta charset=utf-8><title>CAVE</title>"
    "<p>The console hasn't been built. Run <code>pnpm --dir console build</code>.</p>"
)
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; connect-src 'self' wss:; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; worker-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}

router = APIRouter()


@router.get("/assets/{name:path}", include_in_schema=False)
def asset(name: str) -> FileResponse:
    root = (CONSOLE_DIR / "assets").resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(404, "Not found.")
    # Vite puts a content hash in every asset name, so they never change
    return FileResponse(path, headers={"Cache-Control": "public, max-age=31536000, immutable"})


@router.get("/{path:path}", include_in_schema=False)
def spa(path: str) -> Response:
    if path.startswith("api/"):
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    index = CONSOLE_DIR / "index.html"
    if not index.is_file():
        return HTMLResponse(NOT_BUILT)
    return FileResponse(index, headers={"Cache-Control": "no-store"})


def add_security_headers(app: FastAPI) -> None:
    @app.middleware("http")
    async def headers(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)
        if not request.url.path.startswith("/api/"):
            for k, v in SECURITY_HEADERS.items():
                response.headers.setdefault(k, v)
        return response
