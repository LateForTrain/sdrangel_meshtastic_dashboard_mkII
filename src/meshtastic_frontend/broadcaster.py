"""
Module: broadcaster.py
Purpose: Implements a WebSocket broadcaster for real-time message distribution to connected clients

Problem Solved:
This module handles the real-time broadcasting of decoded Meshtastic packets to WebSocket clients, ensuring that messages are delivered promptly and efficiently.

Architectural Role:
This module sits at the core of the application's real-time communication layer, acting as a bridge between the Meshtastic decoder pipeline and WebSocket clients. It is responsible for transforming and distributing data across the network.

Data Flow:

Decoded Meshtastic packets are received from the decoder pipeline.
These packets are mapped to WebSocket message types using a predefined type map.
The messages are then broadcasted to all active WebSocket connections.
Any failed connections are cleaned up to maintain system health.
Primary Responsibilities:

Receiving and processing decoded Meshtastic packets
Mapping packet types to WebSocket message types
Broadcasting messages to all active WebSocket connections
Managing connection health and cleanup
Handling errors and logging for robustness
Assumptions:

The broadcast_queue and active_connections are maintained correctly by other parts of the application.
WebSocket connections are properly managed and closed when no longer needed.
The DecodedMeshPacket class is correctly structured and populated with data from the Meshtastic decoder pipeline.
Considerations for Future Developers:

Avoid modifying the type_map without understanding the implications on message types.
Ensure that the broadcast_queue and active_connections are updated correctly to prevent data inconsistencies.
Be cautious when handling exceptions to avoid disrupting the broadcasting process.
Maintain the logging for debugging and monitoring purposes.
"""

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
            item = await broadcast_queue.get()

            if not active_connections:
                broadcast_queue.task_done()
                continue

            if isinstance(item, dict):
                # Already shaped as a WS message (e.g. sdr_status)
                message = json.dumps(item)
            else:
                # DecodedMeshPacket from the mesh decoder pipeline
                port = item.packet_type
                if port not in type_map:
                    broadcast_queue.task_done()
                    continue

                message = json.dumps({
                    "type":    type_map[port],
                    "payload": item.packet,
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
