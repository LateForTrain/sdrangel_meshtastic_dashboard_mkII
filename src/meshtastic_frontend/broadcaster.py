"""This module contains the implementation of the broadcaster"""

import asyncio
import logging
import json
from .queues import broadcast_queue, active_connections
from .models import DecodedMeshPacket

logger = logging.getLogger(__name__)

async def broadcaster_task():
    """Dedicated broadcaster for WebSocket clients"""
    logger.info("WebSocket Broadcaster Task started")

    type_map = {
                "TEXT_MESSAGE_APP": "new_message",
                "POSITION_APP":     "position_update",
                "TELEMETRY_APP":    "telemetry_update",
                "NODEINFO_APP":     "node_update",
            }
    
    while True:
        try:
            packet: DecodedMeshPacket = await broadcast_queue.get()

            if not active_connections:
                broadcast_queue.task_done()
                continue

            port = packet.packet_type
            if port not in ("TEXT_MESSAGE_APP", "POSITION_APP", "TELEMETRY_APP", "NODEINFO_APP"):
                broadcast_queue.task_done()
                continue

            message = json.dumps({
                "type":    type_map[port],
                "payload": packet.packet,  # already a flat dict with all fields
            })

            dead = []
            for websocket in list(active_connections):
                try:
                    await websocket.send_text(message)
                except Exception:
                    dead.append(websocket)

            for d in dead:
                active_connections.discard(d)

            broadcast_queue.task_done()

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Broadcaster error: {e}", exc_info=True)
            await asyncio.sleep(1)