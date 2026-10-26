from fastapi import FastAPI

from cave.access.items import seed_builtins
from cave.api import admin, auth, entities, ws
from cave.db import Database
from cave.settings import Settings
from cave.state import EventBus, StateMachine


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="CAVE", version="0.1.0")
    app.state.settings = settings
    app.state.db = Database.open(settings.db_path)
    seed_builtins(app.state.db)
    app.state.pending_mfa = {}
    app.state.bus = EventBus()
    app.state.states = StateMachine(app.state.bus)

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth.router)
    app.include_router(entities.router)
    app.include_router(ws.router)
    app.include_router(admin.router)
    return app
