"""This module contains the implementation of the broadcaster"""

import asyncio
import logging
import json
from .queues import broadcast_queue, active_connections
from .models import AppEvent

logger = logging.getLogger(__name__)

                # try:
                #     await broadcast_queue.put(AppEvent(
                #         event_type="new_message",
                #         payload={
                #             "timestamp": message.timestamp.strftime("%H:%M:%S"),
                #             "from_node": f"0x{message.from_node:08x}",
                #             "text": message.text[:200],
                #             "channel": message.channel,
                #         }
                #     ))
                # except Exception as e:
                #     logger.warning(f"Broadcast failed: {e}")


async def broadcaster_task():
    """Dedicated broadcaster for WebSocket clients"""
    logger.info("WebSocket Broadcaster Task started")

    while True:
        try:
            event: AppEvent = await broadcast_queue.get()

            if not active_connections:
                broadcast_queue.task_done()
                continue

            dead = []
            for websocket in list(active_connections):
                try:
                    if event.event_type == "new_message":
                        await websocket.send_text(json.dumps({
                            "type": "new_message",
                            "payload": event.payload
                        }))
                except Exception:
                    dead.append(websocket)

            # Remove dead connections
            for d in dead:
                active_connections.discard(d)

            broadcast_queue.task_done()

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Broadcaster error: {e}", exc_info=True)
            await asyncio.sleep(1)