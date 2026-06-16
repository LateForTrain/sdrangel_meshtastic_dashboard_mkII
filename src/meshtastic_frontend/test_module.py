"""
test_msg.py — Load a test fixture from JSON and inject it onto the queues,
bypassing the full decoder pipeline.

Usage:
    python -m app.test_msg                                      # default fixture
    python -m app.test_msg test_fixtures/position.json          # specific fixture

Available fixtures (put them next to this file):
    test_fixtures/text_message.json
    test_fixtures/position.json
    test_fixtures/nodeinfo.json
    test_fixtures/telemetry_device.json
    test_fixtures/telemetry_environment.json
"""

import asyncio
import json
import sys
from pathlib import Path

from .models import DecodedMeshPacket
from .queues import db_queue, broadcast_queue

# ── Defaults ──────────────────────────────────────────────────────────────────


#TEST_MSG = Path(__file__).parent.parent.parent / "tests/test_fixtures/text_message.json"
TEST_MSG = Path(__file__).parent.parent.parent / "tests/test_fixtures/position.json"
#TEST_MSG = Path(__file__).parent.parent.parent / "tests/test_fixtures/node.json"
#TEST_MSG = Path(__file__).parent.parent.parent / "tests/test_fixtures/tel_dev.json"
#TEST_MSG = Path(__file__).parent.parent.parent / "tests/test_fixtures/tel_env.json"

# Fields that decode_payload() always emits; anything missing from the JSON
# fixture is filled with None so downstream consumers never see a KeyError.
_PAYLOAD_DEFAULTS = {
    "portnum":          None,
    "portnum_id":       None,
    "decode_error":     None,
    "raw_payload_hex":  None,
    "text":             None,
    "latitude":         None,
    "longitude":        None,
    "altitude":         None,
    "precision":        None,
    "gps_time":         None,
    "node_id":          None,
    "long_name":        None,
    "short_name":       None,
    "hw_model":         None,
    "battery":          None,
    "voltage":          None,
    "channel_util":     None,
    "air_util_tx":      None,
    "uptime_seconds":   None,
    "temperature":      None,
    "humidity":         None,
    "pressure":         None,
    "iaq":              None,
    "snr":              None,
    "rssi":             None,
}

# ─────────────────────────────────────────────────────────────────────────────


def load_fixture(path: Path) -> DecodedMeshPacket:
    with open(path) as f:
        fixture = json.load(f)

    header  = fixture["header"]
    payload = {**_PAYLOAD_DEFAULTS, **fixture["payload"]}   # fill missing fields
    was_encrypted = fixture.get("was_encrypted", False)

    packet_dict = {**header, **payload, "was_encrypted": was_encrypted}

    return DecodedMeshPacket(
        packet=packet_dict,
        raw_bytes=b"",
        node_id=header["from_int"],
        packet_type=payload.get("portnum", "UNKNOWN"),
    )


async def inject_test_packet():
    counter = 0

    while True:
        await asyncio.sleep(10)
        decoded_packet = load_fixture(TEST_MSG)
        
        counter += 1
        decoded_packet.packet["id"] = decoded_packet.packet.get("id") + counter
        
        if decoded_packet.packet.get("portnum") == "TEXT_MESSAGE_APP":
            base_text = decoded_packet.packet.get("text")
            decoded_packet.packet["text"] = f"{base_text} [{counter}]"

        if decoded_packet.packet.get("portnum") == "POSITION_APP":
            decoded_packet.packet["longitude"] = decoded_packet.packet["longitude"] + (counter/10)
        
        await db_queue.put(decoded_packet)
        await broadcast_queue.put(decoded_packet)

        print(f"[test_msg] Injected {decoded_packet.packet_type} packet")