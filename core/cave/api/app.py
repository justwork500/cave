from fastapi import FastAPI

from cave.api import auth, entities
from cave.db import Database
from cave.settings import Settings
from cave.state import EventBus, StateMachine


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="CAVE", version="0.1.0")
    app.state.settings = settings
    app.state.db = Database.open(settings.db_path)
    app.state.pending_mfa = {}
    app.state.bus = EventBus()
    app.state.states = StateMachine(app.state.bus)

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth.router)
    app.include_router(entities.router)
    return app
