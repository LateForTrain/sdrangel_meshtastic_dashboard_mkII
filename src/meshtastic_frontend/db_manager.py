"""Module Description: This module contains the implementation of the database manager used to store and retrieve data related to Meshtastic."""
#  General inports
import asyncio
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List

# SQLAlchemy imports
from sqlalchemy import select, Index, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# App imports
from .config import config

from .models import DecodedMeshPacket, TextMessage, Telemetry
from .queues import db_queue

logger = logging.getLogger(__name__)

# ========================== DATABASE SETUP ==========================

DATA_DIR = Path(config.db_dir)
DATA_NAME = config.db_name

DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / DATA_NAME
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH.absolute()}"


# DATABASE MODELS
class Base(DeclarativeBase):
    pass

class DBNode(Base):
    __tablename__ = "node"
    node_id: Mapped[int] = mapped_column(primary_key=True)
    long_name: Mapped[Optional[str]]
    short_name: Mapped[Optional[str]]
    hw_model: Mapped[Optional[str]]
    first_seen: Mapped[datetime]
    last_seen: Mapped[datetime]
    channel: Mapped[Optional[str]]

class DBPosition(Base):
    __tablename__ = "positions"
    #id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    node_id: Mapped[int] = mapped_column(primary_key=True)
    latitude: Mapped[float]
    longitude: Mapped[float]
    altitude: Mapped[Optional[int]]
    timestamp: Mapped[datetime]
    precision: Mapped[Optional[int]]
    gps_time: Mapped[Optional[datetime]]

class DBTextMessage(Base):
    __tablename__ = "text_messages"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    node_id: Mapped[int]
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

    __table_args__ = (
        Index('idx_telemetry_node_time', 'node_id', 'timestamp'),
    )

# Engine & Session
async_engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(async_engine, expire_on_commit=False)

async def init_db():
    """
    Init for db manager
    """
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info(f"Database initialized → {DB_PATH}")

async def upsert_node(session: AsyncSession, decoded: DecodedMeshPacket):
    """
    Update or insert node information
    
    Args:
        session (AsyncSession): The database session
        decoded (DecodedMeshPacket): The decoded packet to be updated
    """

    p = decoded.packet
    result = await session.execute(select(DBNode).where(DBNode.node_id == p.get('from_int')))
    existing = result.scalar_one_or_none()

    if existing:
        existing.last_seen = datetime.now()
        existing.long_name = p.get('long_name') or existing.long_name
        existing.short_name = p.get('short_name') or existing.short_name
        existing.hw_model = p.get('hw_model') or existing.hw_model
        existing.channel = p.get('channel') or existing.channel
    else:
        new_node = DBNode(
            node_id=p.get('from_int'),
            long_name=p.get('long_name'),
            short_name=p.get('short_name'),
            hw_model=p.get('hw_model'),
            first_seen=datetime.now(),
            last_seen=datetime.now(),
            channel=p.get('channel'),
        )
        session.add(new_node)

async def upsert_position(session: AsyncSession, position: DecodedMeshPacket):
    """
    Update or insert position information
    
    Args:
        session (AsyncSession): The database session
        position (Position): The position data to be updated
    """

    p = position.packet
    result = await session.execute(select(DBPosition).where(DBPosition.node_id == p.get('from_int')))
    existing = result.scalar_one_or_none()
    
    if existing:
        existing.latitude = p.get('latitude')
        existing.longitude = p.get('longitude')
        existing.altitude = p.get('altitude')
        existing.timestamp = datetime.now()
        existing.precision = p.get('precision')
        existing.gps_time = datetime.fromisoformat(p.get('gps_time'))
    else:
        new_position = DBPosition(
            node_id=p.get('from_int'),
            latitude=p.get('latitude'),
            longitude=p.get('longitude'),
            altitude=p.get('altitude'),
            timestamp=datetime.now(),
            precision=p.get('precision'),
            gps_time=datetime.fromisoformat(p.get('gps_time')),
        )
        session.add(new_position)

async def save_decoded_packet(decoded: DecodedMeshPacket):
    """
    Main function to save decoded packet to database
    
    Args:
        decoded (DecodedMeshPacket): The decoded packet to be saved
    """
    if not decoded.node_id:
        return

    async with AsyncSessionLocal() as session:
        try:
            await upsert_node(session, decoded)

            p = decoded.packet
            portnum = p.get("portnum")

            if portnum == "POSITION_APP":
                await upsert_position(session, decoded)

            elif portnum == "TEXT_MESSAGE_APP":
                message = TextMessage(
                    node_id=p.get('from_int'),
                    from_node=p.get('from'),
                    to_node=p.get('to'),
                    text=p.get('text', ''),
                    timestamp=datetime.now(),
                    channel=p.get('channel'),
                    packet_id=p.get('id'),
                )
                db_msg = DBTextMessage(**message.__dict__)
                session.add(db_msg)

            elif portnum == "TELEMETRY_APP":
                telemetry = Telemetry(
                    node_id=p.get('from_int'),
                    telemetry_type= "DEVICE",
                    timestamp=datetime.now(),
                    
                    # Device metrics
                    battery=p.get('battery',None),
                    voltage=p.get('voltage',None),
                    channel_util=p.get('channel_util',None),
                    air_util_tx=p.get('air_util_tx',None),
                    uptime_seconds=p.get('uptime_seconds',None),
                    
                    # Environment metrics
                    temperature=p.get('temperature',None),
                    humidity=p.get('humidity',None),
                    pressure=p.get('pressure',None),
                    iaq=p.get('iaq',None),
    
                    # Signal metrics
                    snr=p.get('snr',None),
                    rssi=p.get('rssi',None),
                )
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
    """
    Simple query to get recent text messages for the dashboard
    
    Args:
        limit (int): Number of messages to retrieve.
    
    Return:
        List[dict]: List of recent messages.
    """
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
   
async def get_telemetry_nodes() -> List[dict]:
    """
    Nodes that have ever sent telemetry, with their latest known battery %,
    for the telemetry page's right-hand node list.
    """
    async with AsyncSessionLocal() as session:
        try:
            # "Latest non-null battery per node" — a plain latest-row-per-node
            # query would give nulls half the time, since battery and
            # temperature/humidity arrive in separate packets.
            ranked = (
                select(
                    DBTelemetry.node_id,
                    DBTelemetry.battery,
                    func.row_number()
                    .over(
                        partition_by=DBTelemetry.node_id,
                        order_by=DBTelemetry.timestamp.desc(),
                    )
                    .label("rn"),
                )
                .where(DBTelemetry.battery.is_not(None))
                .subquery()
            )
            latest_battery = (
                select(ranked.c.node_id, ranked.c.battery)
                .where(ranked.c.rn == 1)
                .subquery()
            )

            telemetry_node_ids = select(DBTelemetry.node_id).distinct().subquery()

            stmt = (
                select(DBNode.node_id, DBNode.long_name, latest_battery.c.battery)
                .join(telemetry_node_ids, telemetry_node_ids.c.node_id == DBNode.node_id)
                .outerjoin(latest_battery, latest_battery.c.node_id == DBNode.node_id)
                .order_by(DBNode.long_name)
            )

            result = await session.execute(stmt)
            rows = result.all()

            return [
                {"node_id": r.node_id, "long_name": r.long_name, "battery": r.battery}
                for r in rows
            ]
        except Exception as e:
            logger.error(f"Failed to fetch telemetry node list: {e}")
            return []

async def get_telemetry_history(node_id: int, start: datetime, end: datetime) -> List[dict]:
    """
    Telemetry rows for one node within a time window, ascending by timestamp,
    for the telemetry page's charts.
    """
    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                select(DBTelemetry)
                .where(
                    DBTelemetry.node_id == node_id,
                    DBTelemetry.timestamp >= start,
                    DBTelemetry.timestamp <= end,
                )
                .order_by(DBTelemetry.timestamp.asc())
            )
            rows = result.scalars().all()

            return [
                {
                    "timestamp": r.timestamp.isoformat(),
                    "battery": r.battery,
                    "voltage": r.voltage,
                    "channel_util": r.channel_util,
                    "air_util_tx": r.air_util_tx,
                    "uptime_seconds": r.uptime_seconds,
                    "temperature": r.temperature,
                    "humidity": r.humidity,
                    "pressure": r.pressure,
                    "iaq": r.iaq,
                    "snr": r.snr,
                    "rssi": r.rssi,
                }
                for r in rows
            ]
        except Exception as e:
            logger.error(f"Failed to fetch telemetry history for node {node_id}: {e}")
            return []
        
# ========================== MAIN TASK ==========================
async def db_manager_task():
    """
    Main task for the database manager.
    """
    logger.info("Database Manager Task started")
    await init_db()

    while True:
        try:
            decoded_packet: DecodedMeshPacket = await db_queue.get()
            await save_decoded_packet(decoded_packet)
            db_queue.task_done()

        except asyncio.CancelledError:
            logger.info("DB Manager task cancelled")
            break
        except Exception as e:
            logger.error(f"Unexpected error in DB Manager: {e}", exc_info=True)
            await asyncio.sleep(1)