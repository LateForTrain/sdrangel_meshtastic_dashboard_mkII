import asyncio
from typing import Any
from .models import RawPacketEvent, DecodedMeshPacket, AppEvent

# Central communication queues
raw_packet_queue: asyncio.Queue[RawPacketEvent] = asyncio.Queue(maxsize=1000)
decoded_packet_queue: asyncio.Queue[DecodedMeshPacket] = asyncio.Queue(maxsize=500)
broadcast_queue: asyncio.Queue[AppEvent] = asyncio.Queue(maxsize=500)  # For WebSocket clients