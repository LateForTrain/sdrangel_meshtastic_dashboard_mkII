"""
File Description: This file contains the implementation of the database manager used
to store and retrieve data related to Meshtastic.
"""
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List
from .config import config

# SQLAlchemy imports
from sqlalchemy import select, Index
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .models import (
    DecodedMeshPacket,
    Node,
    Position,
    TextMessage,
    Telemetry,
    AppEvent
)
from .queues import decoded_packet_queue, broadcast_queue

logger = logging.getLogger(__name__)

# ========================== DATABASE SETUP ==========================

DATA_DIR = Path(config.db_dir)
DATA_NAME = config.db_name

DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / DATA_NAME
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH.absolute()}"


class Base(DeclarativeBase):
    pass


# ========================== DATABASE MODELS ==========================

class DBNode(Base):
    __tablename__ = "nodes"
    node_id: Mapped[int] = mapped_column(primary_key=True)
    long_name: Mapped[Optional[str]]
    short_name: Mapped[Optional[str]]
    hw_model: Mapped[Optional[str]]
    first_seen: Mapped[datetime]
    last_seen: Mapped[datetime]
    channel: Mapped[Optional[str]]


class DBPosition(Base):
    __tablename__ = "positions"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    node_id: Mapped[int]
    latitude: Mapped[float]
    longitude: Mapped[float]
    altitude: Mapped[Optional[int]]
    timestamp: Mapped[datetime]
    gps_time: Mapped[Optional[datetime]]
    precision: Mapped[Optional[int]]


class DBTextMessage(Base):
    __tablename__ = "text_messages"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    
    node_id: Mapped[int]           # Sender (for easy querying)
    from_node: Mapped[int]
    to_node: Mapped[int]
    
    text: Mapped[str]
    timestamp: Mapped[datetime]
    channel: Mapped[Optional[str]]
    packet_id: Mapped[Optional[int]]   # Meshtastic packet ID

    # Indexes + unique constraint to prevent duplicate messages
    __table_args__ = (
        Index('idx_messages_node_time', 'node_id', 'timestamp'),
        Index('idx_messages_timestamp', 'timestamp'),
        Index('idx_unique_packet', 'from_node', 'packet_id', unique=True),
    )


class DBTelemetry(Base):
    __tablename__ = "telemetry"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    node_id: Mapped[int]
    telemetry_type: Mapped[str]
    timestamp: Mapped[datetime]

    battery: Mapped[Optional[int]]
    voltage: Mapped[Optional[float]]
    channel_util: Mapped[Optional[float]]
    air_util_tx: Mapped[Optional[float]]
    uptime_seconds: Mapped[Optional[int]]

    temperature: Mapped[Optional[float]]
    humidity: Mapped[Optional[float]]
    pressure: Mapped[Optional[float]]
    iaq: Mapped[Optional[int]]

    snr: Mapped[Optional[float]]
    rssi: Mapped[Optional[int]]


# Engine & Session
async_engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(async_engine, expire_on_commit=False)


async def init_db():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info(f"Database initialized → {DB_PATH}")


# ========================== CONVERSION HELPERS ==========================

def decoded_to_position(decoded: DecodedMeshPacket) -> Position:
    p = decoded.packet
    gps_str = p.get('gps_time')

    gps_time = None
    if isinstance(gps_str, str):
        try:
            # Handle ISO strings with or without timezone
            if gps_str.endswith('Z'):
                gps_str = gps_str.replace('Z', '+00:00')
            gps_time = datetime.fromisoformat(gps_str)
        except Exception as e:
            logger.warning(f"Failed to parse gps_time: {gps_str} - {e}")

    return Position(
        node_id=decoded.node_id,
        latitude=p.get('latitude'),
        longitude=p.get('longitude'),
        altitude=p.get('altitude'),
        timestamp=decoded.timestamp,
        gps_time=gps_time,
        precision=p.get('precision'),
    )


def decoded_to_text_message(decoded: DecodedMeshPacket) -> TextMessage:
    p = decoded.packet
    from_node = decoded.node_id or 0
    to_node = int(p.get('to', '0xffffffff'), 16)

    return TextMessage(
        node_id=from_node,
        from_node=from_node,
        to_node=to_node,
        text=p.get('text', ''),
        timestamp=decoded.timestamp,
        channel=p.get('channel'),
        packet_id=p.get('id'),
    )


def decoded_to_telemetry(decoded: DecodedMeshPacket) -> Telemetry:
    p = decoded.packet
    return Telemetry(
        node_id=decoded.node_id,
        telemetry_type="DEVICE",
        timestamp=decoded.timestamp,
        battery=p.get('battery'),
        voltage=p.get('voltage'),
        channel_util=p.get('channel_util'),
        air_util_tx=p.get('air_util_tx'),
        uptime_seconds=p.get('uptime_seconds'),
        temperature=p.get('temperature'),
        humidity=p.get('humidity'),
        pressure=p.get('pressure'),
        iaq=p.get('iaq'),
        snr=p.get('snr'),
        rssi=p.get('rssi'),
    )


async def upsert_node(session: AsyncSession, decoded: DecodedMeshPacket):
    """Update or insert node information"""
    if not decoded.node_id:
        return

    p = decoded.packet
    result = await session.execute(select(DBNode).where(DBNode.node_id == decoded.node_id))
    existing = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)

    if existing:
        existing.last_seen = now
        existing.long_name = p.get('long_name') or existing.long_name
        existing.short_name = p.get('short_name') or existing.short_name
        existing.hw_model = p.get('hw_model') or existing.hw_model
        existing.channel = p.get('channel') or existing.channel
    else:
        new_node = DBNode(
            node_id=decoded.node_id,
            long_name=p.get('long_name'),
            short_name=p.get('short_name'),
            hw_model=p.get('hw_model'),
            first_seen=now,
            last_seen=now,
            channel=p.get('channel'),
        )
        session.add(new_node)


# ========================== MAIN SAVE FUNCTION ==========================

async def save_decoded_packet(decoded: DecodedMeshPacket):
    """Main function to save decoded packet to database"""
    if not decoded.node_id:
        return

    async with AsyncSessionLocal() as session:
        try:
            await upsert_node(session, decoded)

            p = decoded.packet
            portnum = p.get("portnum")

            if portnum == "POSITION_APP":
                position = decoded_to_position(decoded)
                session.add(DBPosition(**position.__dict__))

            elif portnum == "TEXT_MESSAGE_APP":
                message = decoded_to_text_message(decoded)
                db_msg = DBTextMessage(**message.__dict__)
                session.add(db_msg)

                # Commit all changes (node + message)
                await session.commit()

                # Broadcast only if we reach here (no exception)
                try:
                    await broadcast_queue.put(AppEvent(
                        event_type="new_message",
                        payload={
                            "timestamp": message.timestamp.strftime("%H:%M:%S"),
                            "from_node": f"0x{message.from_node:08x}",
                            "text": message.text[:200],
                            "channel": message.channel,
                        }
                    ))
                except Exception as e:
                    logger.warning(f"Broadcast failed: {e}")

            elif portnum == "TELEMETRY_APP":
                telemetry = decoded_to_telemetry(decoded)
                session.add(DBTelemetry(**telemetry.__dict__))

            await session.commit()

        except IntegrityError as e:
            await session.rollback()
            # Handle duplicate text messages gracefully
            if "idx_unique_packet" in str(e) or "UNIQUE constraint failed" in str(e):
                packet_id = decoded.packet.get('id')
                logger.debug(f"Duplicate text message ignored (from_node={decoded.node_id}, packet_id={packet_id})")
            else:
                logger.warning(f"IntegrityError while saving packet: {e}")
        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to save packet to database: {e}", exc_info=True)


async def get_recent_messages(limit: int = 20) -> List[dict]:
    """Simple query to get recent text messages for the dashboard"""
    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                select(DBTextMessage)
                .order_by(DBTextMessage.timestamp.desc())
                .limit(limit)
            )
            messages = result.scalars().all()

            return [
                {
                    "timestamp": msg.timestamp.strftime("%H:%M:%S"),
                    "from_node": f"0x{msg.from_node:08x}",
                    "text": msg.text,
                    "channel": msg.channel,
                }
                for msg in messages
            ]
        except Exception as e:
            logger.error(f"Failed to fetch recent messages: {e}")
            return []
        

# ========================== MAIN TASK ==========================

async def db_manager_task():
    logger.info("Database Manager Task started")
    await init_db()

    while True:
        try:
            decoded_packet: DecodedMeshPacket = await decoded_packet_queue.get()
            await save_decoded_packet(decoded_packet)
            decoded_packet_queue.task_done()

        except asyncio.CancelledError:
            logger.info("DB Manager task cancelled")
            break
        except Exception as e:
            logger.error(f"Unexpected error in DB Manager: {e}", exc_info=True)
            await asyncio.sleep(1)