from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from cave.access import netconfig
from cave.access.items import seed_builtins
from cave.api import admin, auth, entities, system, ws
from cave.db import Database
from cave.settings import Settings
from cave.state import EventBus, StateMachine

WEB = Path(__file__).resolve().parent.parent / "web"


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="CAVE", version="0.1.0")
    app.state.settings = settings
    app.state.db = Database.open(settings.db_path)
    seed_builtins(app.state.db)
    netconfig.seed(app.state.db, settings)
    app.state.pending_mfa = {}
    app.state.bus = EventBus()
    app.state.states = StateMachine(app.state.bus)

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/spike", include_in_schema=False)
    def spike() -> FileResponse:
        return FileResponse(WEB / "spike.html")

    app.mount("/static", StaticFiles(directory=WEB, html=False), name="static")

    app.include_router(auth.router)
    app.include_router(entities.router)
    app.include_router(ws.router)
    app.include_router(admin.router)
    app.include_router(system.router)
    return app
