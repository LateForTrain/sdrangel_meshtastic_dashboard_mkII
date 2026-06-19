# routes.py
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import asdict
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect,Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import json
import logging
import asyncio

from ..config import config
from ..queues import active_connections
from ..db_manager import get_recent_messages, get_telemetry_nodes, get_telemetry_history

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
    
    def _resolve_range(hours: Optional[int], start: Optional[datetime], end: Optional[datetime]):
        resolved_end = end or datetime.now()
        if start is not None:
            resolved_start = start
        elif hours is not None:
            resolved_start = resolved_end - timedelta(hours=hours)
        else:
            resolved_start = resolved_end - timedelta(hours=6)
        return resolved_start, resolved_end

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

    @app.get("/telemetry", response_class=HTMLResponse)
    async def page_telemetry(request: Request):
        return templates.TemplateResponse(
            request,
            name="telemetry.html",
            context=_base_ctx(request, "telemetry"),
        )
    
    # API routes
    @app.get("/status")
    async def status():
        return {
            "status":   "online",
            "udp_port": config.udp_port,
            "api_port": config.api_port,
        }

    @app.get("/api/config")
    async def api_config():
        return JSONResponse(asdict(config))
    
    @app.get("/api/telemetry/nodes")
    async def api_telemetry_nodes():
        return await get_telemetry_nodes()

    @app.get("/api/telemetry/{node_id}")
    async def api_telemetry_history(
        node_id: int,
        hours: Optional[int] = Query(None, ge=1),
        start: Optional[datetime] = Query(None),
        end: Optional[datetime] = Query(None),
    ):
        range_start, range_end = _resolve_range(hours, start, end)
        return await get_telemetry_history(node_id, range_start, range_end)
    
    # WebSocket call
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