"""
This module contains data classes used to represent various events and domain models in a networked device management system.
These data classes are designed to organize and structure the data for efficient use throughout the application.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Queue Events 

@dataclass
class RawPacketEvent:
    """Raw data obtained from the Meshtastic Receiver"""
    data: bytes
    timestamp: datetime = field(default_factory=utcnow)
    source_ip: Optional[str] = None
    source_port: Optional[int] = None


@dataclass
class DecodedMeshPacket:
    """Intermediate container after decoding"""
    packet: Dict[str, Any]
    raw_bytes: bytes
    timestamp: datetime = field(default_factory=utcnow)
    node_id: Optional[int] = None
    packet_type: str = "unknown"


# Domain Models (for Database + Dashboard)
@dataclass
class Node:
    """Definition of information related to a Node"""
    node_id: int
    long_name: Optional[str] = None
    short_name: Optional[str] = None
    hw_model: Optional[str] = None
    last_seen: datetime = field(default_factory=utcnow)
    first_seen: datetime = field(default_factory=utcnow)
    channel: Optional[str] = None

@dataclass
class Position:
    """Define of information related to a Node Position"""
    node_id: int
    latitude: float
    longitude: float
    altitude: Optional[int] = None
    timestamp: datetime = field(default_factory=utcnow)
    precision: Optional[int] = None
    gps_time: Optional[datetime] = None


@dataclass
class TextMessage:
    """Definition of information related to a Message rereived"""
    node_id: int                    # Sender (main field for queries)
    from_node: int
    to_node: int
    text: str
    timestamp: datetime = field(default_factory=utcnow)
    channel: Optional[str] = None
    packet_id: Optional[int] = None     # Meshtastic packet ID


@dataclass
class Telemetry:
    """Definition of information related to Telemetry of a Node"""
    node_id: int
    telemetry_type: str = "DEVICE"
    timestamp: datetime = field(default_factory=utcnow)
    
    # Device metrics
    battery: Optional[int] = None
    voltage: Optional[float] = None
    channel_util: Optional[float] = None
    air_util_tx: Optional[float] = None
    uptime_seconds: Optional[int] = None
    
    # Environment metrics
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    pressure: Optional[float] = None
    iaq: Optional[int] = None
    
    # Signal metrics
    snr: Optional[float] = None
    rssi: Optional[int] = None


@dataclass
class AppEvent:
    event_type: str
    payload: Any
    timestamp: datetime = field(default_factory=utcnow)