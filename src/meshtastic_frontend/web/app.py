from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..config import config


def create_app() -> FastAPI:
    app = FastAPI(
        title="Meshtastic SDRangel Frontend",
        description="Real-time dashboard for Meshtastic packets from SDRangel",
        version="0.1.0"
    )

    # Mount templates
    templates = Jinja2Templates(directory="src/meshtastic_frontend/web/templates")

    # Simple homepage
    @app.get("/")
    async def root():
        return {
            "message": "Meshtastic SDRangel Frontend",
            "status": "running",
            "docs": "/docs"
        }

    # Status endpoint
    @app.get("/status")
    async def status():
        return {
            "status": "online",
            "udp_port": config.udp_port,
            "api_port": config.api_port
        }

    return app