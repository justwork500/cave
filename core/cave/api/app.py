"""Builds the FastAPI app: database, stores, services and background tasks wired together at startup."""

import asyncio
import contextlib
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from cave.access import netconfig
from cave.access.items import get_item, seed_builtins
from cave.api import admin, auth, entities, screens, system, ws
from cave.api import areas as areas_api
from cave.api import automations as automations_api
from cave.api import config as config_api
from cave.api import console as console_api
from cave.api import kasa as kasa_api
from cave.api import scripts as scripts_api
from cave.api import setup as setup_api
from cave.api import views as views_api
from cave.automation.effects import LiveEffects
from cave.automation.manager import AutomationManager
from cave.config.store import ConfigStore, write_atomic
from cave.credentials import Credentials, load_host_key
from cave.db import Database
from cave.envconfig import env_secret
from cave.integrations.kasa.service import KasaService
from cave.integrations.mqtt import config as mqtt_config
from cave.integrations.mqtt.client import MqttService
from cave.scripts.service import RunnerClient, ScriptService
from cave.scripts.store import ScriptStore
from cave.settings import Settings
from cave.state import EventBus, StateMachine

WEB = Path(__file__).resolve().parent.parent / "web"
log = logging.getLogger(__name__)
STARTER_HOME = """dashboard:
  title: Home
  icon: home
  views:
    - id: main
      title: Main
      sections:
        - title: Getting started
          cards:
            - type: markdown
              content: "This is your Home dashboard. An Admin can change it under Dashboards, Home, Edit."
"""


def _report_mqtt_exit(task: "asyncio.Task[None]") -> None:
    if not task.cancelled() and task.exception() is not None:
        log.error("MQTT stopped unexpectedly: %s", task.exception())


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Starts MQTT when config/mqtt.yaml exists. A broken MQTT config never stops CAVE starting."""
    settings: Settings = app.state.settings
    task = None
    try:
        cfg = mqtt_config.load(settings.config_dir / "mqtt.yaml")
    except mqtt_config.ConfigError as e:
        log.error("MQTT not started: %s", e)
        app.state.mqtt_error = str(e)
        cfg = None
    if cfg is not None:
        service = MqttService(cfg, app.state.db, app.state.states, env_secret("CAVE_MQTT_PASSWORD"))
        app.state.mqtt = service
        task = asyncio.create_task(service.run())
        task.add_done_callback(_report_mqtt_exit)
    effects = LiveEffects(app.state.states, app.state.db, app.state.bus,
                          lambda: app.state.mqtt.bridge if app.state.mqtt else None, scripts=app.state.script_service)
    manager = AutomationManager(app.state.config, app.state.db, app.state.states, app.state.bus, effects)
    app.state.automations = manager
    app.state.rearm = manager.rearm
    await manager.start()
    kasa_task = asyncio.create_task(app.state.kasa.run())
    try:
        yield
    finally:
        kasa_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await kasa_task
        await manager.stop()
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="CAVE", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.mqtt = None
    app.state.mqtt_error = None
    app.state.automations = None
    app.state.rearm = None
    app.state.db = Database.open(settings.db_path)
    fresh = get_item(app.state.db, "dashboard:home") is None
    seed_builtins(app.state.db)
    home = settings.config_dir / "dashboards" / "home.yaml"
    if fresh and not home.exists():  # first start only: a Home an Admin deleted stays deleted
        write_atomic(home, STARTER_HOME)
    netconfig.seed(app.state.db, settings)
    app.state.credentials = Credentials(app.state.db, load_host_key(settings.db_path))
    app.state.pending_mfa = {}
    app.state.bus = EventBus()
    app.state.states = StateMachine(app.state.bus)
    app.state.kasa = KasaService(app.state.db, app.state.states)
    app.state.kasa.load()
    app.state.config = ConfigStore(settings.config_dir, app.state.db, app.state.bus)
    app.state.config.load_all()
    app.state.scripts = ScriptStore(settings.config_dir, app.state.db, app.state.bus)
    app.state.scripts.load_all()
    runner_url, runner_token = os.environ.get("CAVE_RUNNER_URL"), env_secret("CAVE_RUNNER_TOKEN")
    runner = RunnerClient(runner_url, runner_token).post if runner_url and runner_token else None
    app.state.script_service = ScriptService(app.state.scripts, app.state.db, runner)

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/spike", include_in_schema=False)
    def spike() -> FileResponse:
        return FileResponse(WEB / "spike.html")

    @app.get("/enroll", include_in_schema=False)
    def enroll_page() -> FileResponse:
        return FileResponse(WEB / "enroll.html")

    app.mount("/static", StaticFiles(directory=WEB, html=False), name="static")

    app.include_router(auth.router)
    app.include_router(setup_api.router)
    app.include_router(entities.router)
    app.include_router(areas_api.router)
    app.include_router(kasa_api.router)
    app.include_router(views_api.router)
    app.include_router(ws.router)
    app.include_router(admin.router)
    app.include_router(system.router)
    app.include_router(screens.router)
    app.include_router(scripts_api.router)
    app.include_router(automations_api.router)
    app.include_router(config_api.router)  # last: its /{kinds} routes must not shadow the others
    app.include_router(console_api.router)  # very last: it serves the console for any other path
    console_api.add_security_headers(app)
    return app
