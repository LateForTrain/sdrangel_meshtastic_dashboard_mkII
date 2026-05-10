"""This file contains the implementation of queues used for communication.
"""
import asyncio
from .models import RawPacketEvent, DecodedMeshPacket, AppEvent

raw_packet_queue: asyncio.Queue[RawPacketEvent] = asyncio.Queue(maxsize=1000)
decoded_packet_queue: asyncio.Queue[DecodedMeshPacket] = asyncio.Queue(maxsize=500)
broadcast_queue: asyncio.Queue[AppEvent] = asyncio.Queue(maxsize=500)
