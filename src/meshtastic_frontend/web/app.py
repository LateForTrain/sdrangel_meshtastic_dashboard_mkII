from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from ..config import config


def create_app(lifespan=None) -> FastAPI:
    app = FastAPI(
        title="Meshtastic SDRangel Frontend",
        description="Real-time dashboard for Meshtastic packets from SDRangel",
        version="0.1.0",
        lifespan=lifespan
    )

    # Mount templates
    templates = Jinja2Templates(directory="src/meshtastic_frontend/web/templates")

    #Mount static files (CSS, JS, images later)
    static_path = Path("src/meshtastic_frontend/web/static")
    static_path.mkdir(parents=True, exist_ok=True)
    
    app.mount("/static", StaticFiles(directory=static_path), name="static")

    # Simple homepage
    @app.get("/", response_class=HTMLResponse)
    async def root():
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Meshtastic SDRangel Dashboard</title>
            <style>
                body { font-family: system-ui, sans-serif; background: #0f172a; color: #e2e8f0; padding: 20px; }
                h1 { color: #60a5fa; }
                .card { background: #1e2937; padding: 20px; border-radius: 8px; margin: 10px 0; }
            </style>
        </head>
        <body>
            <h1>🚀 Meshtastic SDRangel Frontend</h1>
            <div class="card">
                <h2>Status: <span style="color:#4ade80">Running</span></h2>
                <p>UDP Port: <strong>""" + str(config.udp_port) + """</strong></p>
                <p>Waiting for packets from SDRangel...</p>
            </div>
            <p><a href="/docs">FastAPI Docs</a></p>
        </body>
        </html>
        """

    # Status endpoint
    @app.get("/status")
    async def status():
        return {
            "status": "online",
            "udp_port": config.udp_port,
            "api_port": config.api_port
        }

    return app