from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import asyncio
import json
import logging

from ..config import config
from ..queues import active_connections
from ..db_manager import get_recent_messages

logger = logging.getLogger(__name__)

def create_app(lifespan=None) -> FastAPI:
    app = FastAPI(
        title="Meshtastic SDRangel Frontend",
        version="0.1.0",
        lifespan=lifespan,
    )

    templates = Jinja2Templates(directory="src/meshtastic_frontend/web/templates")
    static_path = Path("src/meshtastic_frontend/web/static")
    static_path.mkdir(parents=True, exist_ok=True)
    
    app.mount("/static", StaticFiles(directory=static_path), name="static")

    # ====================== ROUTES ======================

    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request):
        """Main dashboard page"""
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"udp_port": config.udp_port}
        )

    @app.get("/status")
    async def status():
        return {
            "status": "online",
            "udp_port": config.udp_port,
            "api_port": config.api_port
        }

    # ====================== WEBSOCKET ======================

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """WebSocket endpoint using active_connections"""
        await websocket.accept()
        active_connections.add(websocket)
        
        try:
            # Send recent messages on connect
            recent = await get_recent_messages(limit=15)
            await websocket.send_text(json.dumps({
                "type": "history",
                "messages": recent
            }))

            # Keep connection alive (the broadcaster will push new messages)
            while True:
                await asyncio.sleep(30)   # heartbeat

        except WebSocketDisconnect:
            logger.debug("Client disconnected")
        except Exception as e:
            logger.error(f"WebSocket error: {e}", exc_info=True)
        finally:
            active_connections.discard(websocket)

    return app