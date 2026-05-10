import logging
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import json

from ..config import config
from ..queues import broadcast_queue
from ..db_manager import get_recent_messages

logger = logging.getLogger(__name__)

def create_app(lifespan=None) -> FastAPI:
    """Create a FastAPI application instance.
    """
    app = FastAPI(
        title="Meshtastic SDRangel Frontend",
        version="0.1.0",
        lifespan=lifespan,
    )

    templates = Jinja2Templates(directory="src/meshtastic_frontend/web/templates")
    static_path = Path("src/meshtastic_frontend/web/static")
    static_path.mkdir(parents=True, exist_ok=True)
    
    app.mount("/static", StaticFiles(directory=static_path), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request):
        """Render the index.html template.
        """
        return templates.TemplateResponse(
                    request=request,
                    name="index.html",
                    context={}
                )
    
    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request):
        """Render the index.html template with UDP port information.
        """
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"udp_port": config.udp_port}
        )

    # Status endpoint
    @app.get("/status")
    async def status():
        """Return the status of the application.
        """
        return {
            "status": "online",
            "udp_port": config.udp_port,
            "api_port": config.api_port
        }

    # WebSocket endpoint
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """Handle WebSocket connections.
        """
        await websocket.accept()
        try:
            # Send recent messages on connect
            recent = await get_recent_messages(limit=15)
            await websocket.send_text(json.dumps({
                "type": "history",
                "messages": recent
            }))

            # Listen for new messages from broadcast queue
            while True:
                event = await broadcast_queue.get()
                if event.event_type == "new_message":
                    await websocket.send_text(json.dumps({
                        "type": "new_message",
                        "payload": event.payload
                    }))
                broadcast_queue.task_done()

        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.error(f"Unexpected error in decoder loop: {e}", exc_info=True)
            
    return app