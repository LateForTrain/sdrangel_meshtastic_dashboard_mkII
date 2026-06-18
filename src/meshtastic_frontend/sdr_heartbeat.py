"""SDRangel REST API status monitor

Polls SDRangel's REST API to determine whether it's running and actively
configured to send Meshtastic-decoded data via UDP. This is a meaningfully
stronger signal than the UDP transport check, since it asks SDRangel directly
rather than inferring from a one-way channel that may simply be carrying no
traffic.

"Connected" requires all three:
  1. SDRangel REST API is reachable
  2. A device set has a channel with id "MeshtasticDemod", and that device's
     sampling device state is "running"
  3. That channel's settings have sendViaUDP == 1 (or sendJsonViaUDP == 1)
"""

import asyncio
import logging
import aiohttp

from .config import config
from .queues import broadcast_queue

logger = logging.getLogger(__name__)

SDRANGEL_BASE_URL = "http://127.0.0.1:8091/sdrangel"
POLL_INTERVAL_SECONDS = 5
REQUEST_TIMEOUT_SECONDS = 3
TARGET_CHANNEL_ID = "MeshtasticDemod"


async def _find_meshtastic_channel(session: aiohttp.ClientSession):
    """
    Searches all device sets for a channel with id "MeshtasticDemod".
    Returns (deviceset_index, channel_index, device_state) or None if not found
    or SDRangel is unreachable.
    """
    try:
        async with session.get(
            SDRANGEL_BASE_URL,
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
        ) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return None

    device_sets = data.get("devicesetlist", {}).get("deviceSets", [])

    for ds_index, device_set in enumerate(device_sets):
        for channel in device_set.get("channels", []):
            if channel.get("id") == TARGET_CHANNEL_ID:
                device_state = device_set.get("samplingDevice", {}).get("state")
                return ds_index, channel.get("index"), device_state

    return None


async def _check_channel_sending_udp(
    session: aiohttp.ClientSession, ds_index: int, ch_index: int
) -> bool:
    """Checks whether the given channel is configured to send via UDP."""
    url = f"{SDRANGEL_BASE_URL}/deviceset/{ds_index}/channel/{ch_index}/settings"
    try:
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
        ) as resp:
            if resp.status != 200:
                return False
            data = await resp.json()
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return False

    settings = data.get(f"{TARGET_CHANNEL_ID}Settings", {})
    return settings.get("sendViaUDP") == 1 or settings.get("sendJsonViaUDP") == 1


async def check_sdrangel_status(session: aiohttp.ClientSession) -> dict:
    """
    Returns a status dict describing SDRangel's current state, used both for
    broadcasting and for logging/debugging which stage failed.
    """
    found = await _find_meshtastic_channel(session)

    if found is None:
        return {
            "reachable": False,
            "device_running": False,
            "sending_udp": False,
            "connected": False,
        }

    ds_index, ch_index, device_state = found
    device_running = device_state == "running"

    sending_udp = False
    if device_running:
        sending_udp = await _check_channel_sending_udp(session, ds_index, ch_index)

    return {
        "reachable": True,
        "device_running": device_running,
        "sending_udp": sending_udp,
        "connected": device_running and sending_udp,
    }


async def sdr_status_monitor_task():
    """Periodically polls SDRangel and broadcasts status changes."""
    logger.info("Starting SDR status monitor task...")
    last_status: dict | None = None

    async with aiohttp.ClientSession() as session:
        while True:
            status = await check_sdrangel_status(session)
            
            await broadcast_queue.put({
                    "type": "sdr_status",
                    "payload": {
                        "connected": status["connected"],
                        "reachable": status["reachable"],
                        "device_running": status["device_running"],
                        "sending_udp": status["sending_udp"],
                        "port": config.udp_port,
                    }
            })

            await asyncio.sleep(POLL_INTERVAL_SECONDS)