"""
This file contains the implementation of queues used for communication.
"""
import asyncio
from typing import Any, Set
from .models import RawPacketEvent, DecodedMeshPacket, AppEvent

# Main queues
raw_packet_queue: asyncio.Queue[RawPacketEvent] = asyncio.Queue(maxsize=1000)
decoded_packet_queue: asyncio.Queue[DecodedMeshPacket] = asyncio.Queue(maxsize=500)

# For WebSocket broadcasting
broadcast_queue: asyncio.Queue[AppEvent] = asyncio.Queue(maxsize=200)

# Keep track of active WebSocket connections
active_connections: Set = set()