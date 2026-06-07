# app.py

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import logging

from .routes import add_routes  # Import the routes function

logger = logging.getLogger(__name__)

def create_app(lifespan=None) -> FastAPI:
    app = FastAPI(
        title="Meshtastic SDRangel Frontend",
        version="0.1.0",
        lifespan=lifespan,
    )

    templates = Jinja2Templates(
        directory="src/meshtastic_frontend/web/templates"
    )

    # Ensure the static directory exists before mounting
    BASE_DIR = Path(__file__).resolve().parent  # points to the 'web' folder
    static_dir = BASE_DIR / "static"

    # Create directory if it doesn't exist
    static_dir.mkdir(parents=True, exist_ok=True)

    app.mount(
        "/static",
        StaticFiles(directory=static_dir),
        name="static"
    )

    add_routes(app, templates)  # Add routes to the app

    return app
