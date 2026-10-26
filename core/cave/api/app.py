from fastapi import FastAPI

from cave.settings import Settings


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="CAVE", version="0.1.0")
    app.state.settings = settings

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
