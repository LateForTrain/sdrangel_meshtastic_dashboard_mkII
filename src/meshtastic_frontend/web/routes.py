# routes.py

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import json
import logging
import asyncio

from ..config import config
from ..queues import active_connections
from ..db_manager import get_recent_messages

logger = logging.getLogger(__name__)

def add_routes(app: FastAPI, templates: Jinja2Templates):

    # Shared template context
    def _base_ctx(request: Request, active_page: str) -> dict:
        return {
            "request":     request,
            "udp_port":    config.udp_port,
            "api_port":    config.api_port,
            "active_page": active_page,
        }

    # Page routes
    @app.get("/", response_class=HTMLResponse)
    async def page_messages(request: Request):
        return templates.TemplateResponse(
            request,
            name="message.html",
            context=_base_ctx(request, "messages"),
        )

    @app.get("/map", response_class=HTMLResponse)
    async def page_map(request: Request):
        return templates.TemplateResponse(
            request,
            name="map.html",
            context=_base_ctx(request, "map"),
        )

    @app.get("/config", response_class=HTMLResponse)
    async def page_config(request: Request):
        return templates.TemplateResponse(
            request,
            name="config.html",
            context=_base_ctx(request, "config"),
        )

    # API routes
    @app.get("/status")
    async def status():
        return {
            "status":   "online",
            "udp_port": config.udp_port,
            "api_port": config.api_port,
        }

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        active_connections.add(websocket)

        try:
            while True:
                await asyncio.sleep(30)

        except WebSocketDisconnect:
            logger.debug("WebSocket: client disconnected normally")
        except Exception as exc:
            logger.error("WebSocket error: %s", exc, exc_info=True)
        finally:
            active_connections.discard(websocket)