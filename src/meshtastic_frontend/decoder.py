"""
File Description: This file contains the implementation of the decoder used for
decoding and processing LoRa packets received from Meshtastic.
"""
import asyncio
import logging
import base64
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from meshtastic import mesh_pb2, portnums_pb2, telemetry_pb2

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

from .config import config
from .models import RawPacketEvent, DecodedMeshPacket
from .queues import raw_packet_queue, decoded_packet_queue

logger = logging.getLogger(__name__)

# Default LongFast channel key (public)
DEFAULT_KEY = base64.b64decode(config.mesh_key)

logger.info("Decoder initialized with default key")


def parse_lora_header(data: bytes) -> Dict[str, Any]:
    """Parse 16-byte LoRa header"""
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
    """Decrypt Meshtastic AES-CTR payload
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
    """Decode protobuf payload - supports most common Meshtastic packet types
    """
    result: Dict[str, Any] = {}

    try:
        data = mesh_pb2.Data()
        data.ParseFromString(plaintext)

        portnum = data.portnum
        result['portnum'] = portnums_pb2.PortNum.Name(portnum)
        result['portnum_id'] = portnum

        # Text Message
        if portnum == portnums_pb2.TEXT_MESSAGE_APP:
            result['text'] = data.payload.decode('utf-8', errors='replace')

        # Position
        elif portnum == portnums_pb2.POSITION_APP:
            pos = mesh_pb2.Position()
            pos.ParseFromString(data.payload)
            result['latitude'] = pos.latitude_i / 1e7
            result['longitude'] = pos.longitude_i / 1e7
            result['altitude'] = pos.altitude
            result['precision'] = pos.precision_bits
            if pos.time:
                result['gps_time'] = datetime.fromtimestamp(pos.time, tz=timezone.utc).isoformat()

        # Node Info
        elif portnum == portnums_pb2.NODEINFO_APP:
            user = mesh_pb2.User()
            user.ParseFromString(data.payload)
            result['node_id'] = user.id
            result['long_name'] = user.long_name
            result['short_name'] = user.short_name
            result['hw_model'] = user.hw_model

        # Telemetry (Most Common)
        elif portnum == portnums_pb2.TELEMETRY_APP:
            tele = telemetry_pb2.Telemetry()
            tele.ParseFromString(data.payload)

            if tele.HasField('device_metrics'):
                m = tele.device_metrics
                result.update({
                    'battery': m.battery_level,
                    'voltage': round(m.voltage, 3),
                    'channel_util': round(m.channel_utilization, 2),
                    'air_util_tx': round(m.air_util_tx, 2),
                    'uptime_seconds': m.uptime_seconds,
                })

            elif tele.HasField('environment_metrics'):
                m = tele.environment_metrics
                result.update({
                    'temperature': round(m.temperature, 2),
                    'humidity': round(m.relative_humidity, 2),
                    'pressure': round(m.barometric_pressure, 2),
                    'gas_resistance': getattr(m, 'gas_resistance', None),
                    'iaq': getattr(m, 'iaq', None),
                })

            elif tele.HasField('power_metrics'):
                m = tele.power_metrics
                result.update({
                    'ch1_voltage': round(m.ch1_voltage, 3),
                    'ch1_current': round(m.ch1_current, 3),
                    'ch2_voltage': round(m.ch2_voltage, 3),
                    'ch2_current': round(m.ch2_current, 3),
                })

            elif tele.HasField('signal_metrics'):
                m = tele.signal_metrics
                result.update({
                    'snr': round(m.snr, 2),
                    'rssi': m.rssi,
                })

        # Traceroute
        elif portnum == portnums_pb2.TRACEROUTE_APP:
            trace = mesh_pb2.RouteDiscovery()
            trace.ParseFromString(data.payload)
            result['route'] = [f'0x{hop:08x}' for hop in trace.route]
            result['snr_towards'] = list(trace.snr_towards)

        # Neighbor Info
        elif portnum == portnums_pb2.NEIGHBORINFO_APP:
            neigh = mesh_pb2.NeighborInfo()
            neigh.ParseFromString(data.payload)
            result['node_id'] = neigh.node_id
            result['neighbors'] = [
                {
                    'node_id': n.node_id,
                    'snr': round(n.snr, 2),
                    'last_rx_time': n.last_rx_time
                } for n in neigh.neighbors
            ]

        # Routing
        elif portnum == portnums_pb2.ROUTING_APP:
            routing = mesh_pb2.Routing()
            routing.ParseFromString(data.payload)
            result['routing_type'] = routing.WhichOneof('variant')
            if routing.HasField('error_reason'):
                result['error_reason'] = mesh_pb2.Routing.Error.Reason.Name(routing.error_reason)

        # Unknown / Raw fallback
        else:
            result['raw_payload_hex'] = data.payload.hex()

    except Exception as e:
        result['decode_error'] = str(e)
        result['raw_payload_hex'] = plaintext.hex()

    return result


async def decoder_task():
    """Background task that decodes raw Meshtastic packets
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
                plaintext = decrypt_payload(
                    encrypted_payload,
                    header['id'],
                    header['from_int'],
                    key
                )

                was_encrypted = plaintext is not None
                if not was_encrypted:
                    plaintext = encrypted_payload

                # Decode content
                decoded_payload = decode_payload(plaintext)

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

                # Put on decoded queue
                await decoded_packet_queue.put(decoded_packet)

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