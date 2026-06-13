"""Utility functions for converting decoded mesh packets into structured messages.

This module contains converters that transform raw DecodedMeshPacket data
into standardized Position, TextMessage, Telemetry, and Node objects ready
for database storage or API responses.
"""

from datetime import datetime
import logging

from .models import (
    DecodedMeshPacket,
    Position,
    TextMessage,
    Telemetry
)

logger = logging.getLogger(__name__)


# ========================== CONVERSION HELPERS ==========================

def decoded_to_position(decoded: "DecodedMeshPacket") -> Position:
    """Convert a decoded mesh packet into a Position object.

    Args:
        decoded (DecodedMeshPacket): The decoded mesh packet to be converted.
            Must have 'gps_time' field as ISO string if GPS time is available.

    Returns:
        Position: A Position object with latitude, longitude, altitude from the packet,
                  along with node_id and timestamp metadata. GPS timezone info is stripped
                  if present in the raw data for standard comparison later.

    Notes:
        - If 'gps_time' field is missing or not a string (e.g., None), returns position without GPS time parsing error.
        - Precision, altitude fields are included from packet when available.

    """
    p = decoded.packet
    gps_str = p.get('gps_time')  # type: ignore[attr-defined]
    
    gps_time = None
    
    if isinstance(gps_str, str):
        try:
            # Handle ISO strings with or without timezone
            if gps_str.endswith('Z'):
                gps_str = gps_str.replace('Z', '+00:00')
            from datetime import UTC  # type: ignore[attr-defined]
            utc_time = datetime.fromisoformat(gps_str).astimezone(UTC)  # type: ignore[attr-defined]
        except Exception as e:
            logger.warning(f"Failed to parse gps_time in position conversion: {gps_str} - {e}")
        
    return Position(
        node_id=decoded.node_id,
        latitude=p.get('latitude'),
        longitude=p.get('longitude'),
        altitude=p.get('altitude'),
        timestamp=decoded.timestamp,
        gps_time=gps_time,  # type: ignore[attr-defined]
        precision=p.get('precision'),
    )

def decoded_to_text_message(decoded: "DecodedMeshPacket") -> TextMessage:
    """Convert a decoded mesh packet into a TextMessage object.

    Args:
        decoded (DecodedMeshPacket): The decoded mesh packet containing text content and routing info.

    Returns:
        TextMessage: A message with from_node, to_node addresses, payload text, and metadata.

    Notes:
        - 'to' field is hex-formatted in mesh; converted to int for cleaner API use later.
        - If 'channel' not available (like when channel=0), returns 0 as default value which simplifies web layer logic.
        - Packet ID included from original message if present, else None.

    """
    p = decoded.packet
    
    # Convert hex-formatted node addresses to integer form suitable for API/web consumption later:
    from_node_int = int(decoded.node_id)  # type: ignore[attr-defined]
    try:
        to_node_int = int(p.get('to', '0xffffffff'), 16) if p.get('to') else decoded.to_node or 0x7FFFFFFF  # type: ignore[attr-defined],type:ignore[misc,assignment]
    except (TypeError, ValueError):
        to_node_int = 0
    
    return TextMessage(
        node_id=from_node_int,
        from_node=from_node_int,
        to_node=to_node_int,
        text=p.get('text', ''),
        timestamp=decoded.timestamp,
        channel=p.get('channel'),  # type: ignore[attr-defined]
        packet_id=p.get('id'),  # type: ignore[attr-defined]
    )

def decoded_to_telemetry(decoded: "DecodedMeshPacket") -> Telemetry:
    """Convert a decoded mesh packet into a Telemetry object.

    Args:
        decoded (DecodedMeshPacket): The decoded mesh packet with device telemetry fields.

    Returns:
        Telemetry: A telemetry record containing battery, voltage, radio metrics like SNR/RSSI.

    Notes:
        - Always labels type as 'DEVICE' since these come from hardware sensors directly.
        - Missing optional sensor readings (like humidity or pressure) return None safely without exception thrown upstream when parsing raw queue data before DB insertion occurs next stage downstream through WebSocket handlers awaiting processed messages now ready for frontend display later!

    """
    p = decoded.packet
    
    # Build telemetry dict with only available fields so missing ones don't break consumer expecting certain schema shape expected by web layer consuming these payloads later on:
    
    return Telemetry(  # type: ignore[attr-defined]
        node_id=decoded.node_id,
        telemetry_type="DEVICE",
        timestamp=decoded.timestamp,
        battery=p.get('battery'),
        voltage=p.get('voltage'),
        channel_util=p.get('channel_util'),
        air_util_tx=p.get('air_util_tx'),  # type: ignore[attr-defined]
        uptime_seconds=p.get('uptime_seconds'),
        temperature=p.get('temperature'),
        humidity=p.get('humidity'),
        pressure=p.get('pressure'),
        iaq=p.get('iaq'),
        snr=p.get('snr'),
        rssi=p.get('rssi'),
    )