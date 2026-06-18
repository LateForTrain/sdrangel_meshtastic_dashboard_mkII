"""UDP listener for Meshtastic messages

This module listens for UDP packets from Meshtastic and sends them to a queue for processing.
The messages are then processed by functions connected to the queue.
"""

import asyncio
import logging
from .config import config
from .models import RawPacketEvent
from .queues import raw_packet_queue

logger = logging.getLogger(__name__)

class MeshtasticUDPProtocol(asyncio.DatagramProtocol):
    def connection_made(self, transport):
        """
        Called when the transport is connected to a remote
        host and port.
        
        Args:
            transport (asyncio.DatagramTransport): The transport object.
        """

        self.transport = transport
        logger.info(f"UDP Listener started on {config.udp_host}:{config.udp_port}")

    def datagram_received(self, data: bytes, addr: tuple[str, int]):
        """
        Called when a datagram is received from the remote host and port.
        
        Args:
            data (bytes): The received datagram.
            addr (tuple[str, int]): The remote host and port.
        """
        try:
            event = RawPacketEvent(
                data=data,
                source_ip=addr[0],
                source_port=addr[1]
            )
            
            raw_packet_queue.put_nowait(event)
            logger.debug(f"Queued {len(data)} bytes from {addr}")

        except asyncio.QueueFull:
            logger.warning(f"Queue full - dropped packet from {addr[0]}")
        except Exception as e:
            logger.error(f"Failed to handle UDP packet: {e}", exc_info=True)

_current_transport: asyncio.DatagramTransport | None = None
_current_protocol: MeshtasticUDPProtocol | None = None

async def udp_listener_task():
    global _current_transport, _current_protocol
    logger.info("Starting Meshtastic UDP Listener Task...")
    loop = asyncio.get_running_loop()

    try:
        transport, protocol = await loop.create_datagram_endpoint(
            MeshtasticUDPProtocol,
            local_addr=(config.udp_host, config.udp_port)
        )
        _current_transport = transport
        _current_protocol = protocol
        logger.info(f"UDP socket bound to {config.udp_host}:{config.udp_port}")

        try:
            while True:
                await asyncio.sleep(3600)
        finally:
            transport.close()
            _current_transport = None
            _current_protocol = None

    except Exception as e:
        logger.error(f"UDP Listener task crashed: {e}", exc_info=True)
        raise

