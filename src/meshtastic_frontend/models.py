from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def utcnow() -> datetime:
    """Timezone-aware UTC now (replacement for deprecated utcnow())"""
    return datetime.now(timezone.utc)


@dataclass
class RawPacketEvent:
    """Raw UDP packet received from SDRangel"""
    data: bytes
    timestamp: datetime = field(default_factory=utcnow)
    source_ip: Optional[str] = None
    source_port: Optional[int] = None


@dataclass
class DecodedMeshPacket:
    """Decoded Meshtastic packet"""
    packet: Dict[str, Any]
    raw_bytes: bytes
    timestamp: datetime = field(default_factory=utcnow)
    node_id: Optional[int] = None
    packet_type: str = "unknown"


@dataclass
class AppEvent:
    """Generic internal event for broadcasting"""
    event_type: str
    payload: Any
    timestamp: datetime = field(default_factory=utcnow)