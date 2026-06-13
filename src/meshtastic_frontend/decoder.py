"""This module contains the implementation of the decoder used for decoding and processing LoRa packets received from Meshtastic.
"""
import asyncio
import logging
import base64
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from meshtastic import mesh_pb2, portnums_pb2, telemetry_pb2

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

from .config import config
from .models import RawPacketEvent, DecodedMeshPacket
from .queues import raw_packet_queue, db_queue, broadcast_queue

logger = logging.getLogger(__name__)

# All possible output fields, grouped by packet type for readability
_RESULT_DEFAULTS: Dict[str, Any] = {
    # Always present
    "portnum":          None,
    "portnum_id":       None,
    "decode_error":     None,
    "raw_payload_hex":  None,

    # TEXT_MESSAGE_APP
    "text":             None,

    # POSITION_APP
    "latitude":         None,
    "longitude":        None,
    "altitude":         None,
    "precision":        None,
    "gps_time":         None,

    # NODEINFO_APP
    "node_id":          None,
    "long_name":        None,
    "short_name":       None,
    "hw_model":         None,

    # TELEMETRY_APP — device_metrics
    "battery":          None,
    "voltage":          None,
    "channel_util":     None,
    "air_util_tx":      None,
    "uptime_seconds":   None,

    # TELEMETRY_APP — environment_metrics
    "temperature":      None,
    "humidity":         None,
    "pressure":         None,
    "iaq":              None,

    # TELEMETRY_APP — signal_metrics
    "snr":              None,
    "rssi":             None,
}

class MeshPacketDeduplicator:
    """
    Lightweight in-memory deduplicator for Meshtastic packets.
    Uses (from_node, packet_id) as the uniqueness key.
    """
    
    def __init__(self, window_seconds: int = 30, max_per_node: int = 2000):
        self.seen = defaultdict(lambda: deque(maxlen=max_per_node))
        self.window_seconds = window_seconds
        self.duplicate_count = 0

    def is_duplicate(self, from_node: int, packet_id: int) -> bool:
        """
        Return True if this (from_node, packet_id) was seen recently.
        
        Args: from_node (int): The node ID of the packet.
              packet_id (int): The packet ID of the packet.
        
        Returns: bool: Indicating whether this packet is a duplicate or not.
        """
        now = time.time()
        key = packet_id
        
        node_queue = self.seen[from_node]

        # Lazy cleanup of old entries
        while node_queue and node_queue[0][0] < now - self.window_seconds:
            node_queue.popleft()

        # Check for duplicate
        for ts, existing_id in node_queue:
            if existing_id == key:
                self.duplicate_count += 1
                return True

        # New packet
        node_queue.append((now, key))
        return False

# Global deduplicator instance
deduplicator = MeshPacketDeduplicator(window_seconds=30)

# Default LongFast channel key (public)
DEFAULT_KEY = base64.b64decode(config.mesh_key)

logger.info("Decoder initialized with default key")

def parse_lora_header(data: bytes) -> Dict[str, Any]:
    """
    Parses the LoRa packet header and returns a dictionary containing the parsed fields.
    
    Args: 
        data (bytes): The raw LoRa packet data.

    Returns: 
        Dict ([str, Any]): A dictionary containing the parsed fields.
    """
    if len(data) < 16:
        raise ValueError(f"Packet too short for header: {len(data)} bytes")

    dest = int.from_bytes(data[0:4], 'little')
    src = int.from_bytes(data[4:8], 'little')
    pkt_id = int.from_bytes(data[8:12], 'little')
    flags = data[12]
    ch_hash = data[13]

    return {
        'to': f'0x{dest:08x}',
        'from': f'0x{src:08x}',
        'from_int': src,
        'id': pkt_id,
        'id_hex': f'0x{pkt_id:08x}',
        'hop_limit': flags & 0x07,
        'want_ack': bool((flags >> 3) & 0x01),
        'via_mqtt': bool((flags >> 4) & 0x01),
        'hop_start': (flags >> 5) & 0x07,
        'channel': f'0x{ch_hash:02x}',
    }

def decrypt_payload(payload: bytes, packet_id: int, from_node: int, key: bytes) -> Optional[bytes]:
    """
    Decrypts the payload of a LoRa packet.
    
    Args:
        payload (bytes): The raw payload of the LoRa packet.
        packet_id (int): The packet ID of the LoRa packet.
        from_node (int): The node ID of the packet.
        key (bytes): The AES key used for decryption.
    
    Returns: 
        Optional [bytes]: The decrypted payload or None if decryption failed.
    """
    try:
        nonce = packet_id.to_bytes(8, 'little') + from_node.to_bytes(8, 'little')
        cipher = Cipher(algorithms.AES(key), modes.CTR(nonce), backend=default_backend())
        decryptor = cipher.decryptor()
        return decryptor.update(payload) + decryptor.finalize()
    except Exception as e:
        logger.debug(f"Decryption failed: {e}")
        return None

def decode_payload(plaintext: bytes) -> Dict[str, Any]:
    """
    Decode protobuf payload - supports most common Meshtastic packet types.

    All possible fields are always present in the returned dict.
    Fields that do not apply to the received packet type are set to None.

    Args:
        plaintext: Decrypted payload bytes.

    Returns:
        Dict with all possible packet fields; irrelevant fields are None.
    """
    result: Dict[str, Any] = dict(_RESULT_DEFAULTS)  # start from a clean copy

    try:
        data = mesh_pb2.Data()
        data.ParseFromString(plaintext)

        portnum = data.portnum
        result["portnum"]    = portnums_pb2.PortNum.Name(portnum)
        result["portnum_id"] = portnum

        # ── Text Message ──────────────────────────────────────────────────────
        if portnum == portnums_pb2.TEXT_MESSAGE_APP:
            result["text"] = data.payload.decode("utf-8", errors="replace")

        # ── Position ──────────────────────────────────────────────────────────
        elif portnum == portnums_pb2.POSITION_APP:
            pos = mesh_pb2.Position()
            pos.ParseFromString(data.payload)
            result["latitude"]  = pos.latitude_i / 1e7
            result["longitude"] = pos.longitude_i / 1e7
            result["altitude"]  = pos.altitude
            result["precision"] = pos.precision_bits
            if pos.time:
                result["gps_time"] = datetime.fromtimestamp(
                    pos.time, tz=timezone.utc
                ).isoformat()

        # ── Node Info ─────────────────────────────────────────────────────────
        elif portnum == portnums_pb2.NODEINFO_APP:
            user = mesh_pb2.User()
            user.ParseFromString(data.payload)
            result["node_id"]    = user.id
            result["long_name"]  = user.long_name
            result["short_name"] = user.short_name
            result["hw_model"]   = user.hw_model

        # ── Telemetry ─────────────────────────────────────────────────────────
        elif portnum == portnums_pb2.TELEMETRY_APP:
            tele = telemetry_pb2.Telemetry()
            tele.ParseFromString(data.payload)

            if tele.HasField("device_metrics"):
                m = tele.device_metrics
                result["battery"]       = m.battery_level
                result["voltage"]       = round(m.voltage, 3)
                result["channel_util"]  = round(m.channel_utilization, 2)
                result["air_util_tx"]   = round(m.air_util_tx, 2)
                result["uptime_seconds"]= m.uptime_seconds

            elif tele.HasField("environment_metrics"):
                m = tele.environment_metrics
                result["temperature"]   = round(m.temperature, 2)
                result["humidity"]      = round(m.relative_humidity, 2)
                result["pressure"]      = round(m.barometric_pressure, 2)
                result["iaq"]           = getattr(m, "iaq", None)

            elif tele.HasField("signal_metrics"):
                m = tele.signal_metrics
                result["snr"]  = round(m.snr, 2)
                result["rssi"] = m.rssi

        # ── Unknown / fallback ────────────────────────────────────────────────
        else:
            result["raw_payload_hex"] = data.payload.hex()

    except Exception as e:
        result["decode_error"]    = str(e)
        result["raw_payload_hex"] = plaintext.hex()

    return result

async def decoder_task():
    """
    Background task that decodes raw Meshtastic packets.
    """
    logger.info("Meshtastic Decoder Task started")

    key = DEFAULT_KEY

    while True:
        try:
            raw_event: RawPacketEvent = await raw_packet_queue.get()

            try:
                data = raw_event.data

                if len(data) < 17:
                    logger.warning(f"Packet too short ({len(data)} bytes) from {raw_event.source_ip}")
                    continue

                # Parse header
                header = parse_lora_header(data)
                encrypted_payload = data[16:]

                # Try decryption
                decrypt_body = decrypt_payload(
                    encrypted_payload,
                    header['id'],
                    header['from_int'],
                    key
                )

                #was_encrypted here means was encrypted with key other than public key
                was_encrypted = decrypt_body is not None
                if not was_encrypted:
                    decrypt_body = encrypted_payload

                # Decode content
                decoded_payload = decode_payload(decrypt_body)

                # Check for duplicates
                if deduplicator.is_duplicate(
                    from_node=header['from_int'],
                    packet_id=header['id']
                ):
                    logger.debug(f"Duplicate packet dropped: from {header['from']} id {header['id_hex']}")
                    continue  # Skip to finally block

                # Build final decoded packet
                packet_dict = {
                    **header,
                    **decoded_payload,
                    'was_encrypted': was_encrypted,
                }

                decoded_packet = DecodedMeshPacket(
                    packet=packet_dict,
                    raw_bytes=data,
                    node_id=header.get('from_int'),
                    packet_type=decoded_payload.get('portnum', 'UNKNOWN')
                )
                
                await db_queue.put(decoded_packet)
                await broadcast_queue.put(decoded_packet)

                # Logging 
                port = decoded_payload.get('portnum', 'UNKNOWN')
                if port != 'UNKNOWN':
                    logger.info(f"Decoded {port} from {header['from']} "
                               f"({len(data)} bytes)")

            except Exception as e:
                logger.error(f"Failed to decode packet from {raw_event.source_ip}: {e}", exc_info=True)

            finally:
                raw_packet_queue.task_done()

        except asyncio.CancelledError:
            logger.info("Decoder task cancelled")
            break
        except Exception as e:
            logger.error(f"Unexpected error in decoder loop: {e}", exc_info=True)
            await asyncio.sleep(1)