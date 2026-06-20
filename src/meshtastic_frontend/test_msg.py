"""
test_msg.py — Accelerated multi-node mesh test injector.

Simulates 3 nodes sending nodeinfo, position, telemetry (device + environment),
and text-message packets onto db_queue / broadcast_queue at randomized intervals,
for a configurable total duration. Bypasses the decoder pipeline, like the
original single-fixture version, but drives several nodes at once so you can
soak-test the dashboard (map, telemetry charts, message log, node list)
without real radio traffic.

Usage:
    python -m app.test_msg
    python -m app.test_msg --duration 900 --min-interval 1 --max-interval 10
    python -m app.test_msg --duration 1200 --min-interval 2 --max-interval 8

Fixture templates (payload-only; header/node identity is synthesized per node):
    test_fixtures/node.json
    test_fixtures/position.json
    test_fixtures/tel_device.json
    test_fixtures/tel_env.json
    test_fixtures/text_message.json
"""

import argparse
import asyncio
import itertools
import json
import random
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .models import DecodedMeshPacket
from .queues import db_queue, broadcast_queue

# ── Paths ────────────────────────────────────────────────────────────────────

FIXTURES_DIR = Path(__file__).parent.parent.parent / "tests/test_fixtures"

TEMPLATE_FILES = {
    "nodeinfo": FIXTURES_DIR / "node.json",
    "position": FIXTURES_DIR / "position.json",
    "telemetry_device": FIXTURES_DIR / "tel_device.json",
    "telemetry_environment": FIXTURES_DIR / "tel_env.json",
    "text_message": FIXTURES_DIR / "text_message.json",
}

# Fields that decode_payload() always emits; anything missing is filled with
# None so downstream consumers never see a KeyError.
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


def _load_payload_template(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)["payload"]


PAYLOAD_TEMPLATES = {k: _load_payload_template(p) for k, p in TEMPLATE_FILES.items()}

# ── Node profiles ────────────────────────────────────────────────────────────


@dataclass
class NodeProfile:
    from_int: int
    node_id_hex: str
    long_name: str
    short_name: str
    hw_model: str
    base_lat: float
    base_lon: float
    base_alt: int = 40
    battery: float = 95.0
    lat: float = field(init=False)
    lon: float = field(init=False)

    def __post_init__(self):
        self.lat = self.base_lat
        self.lon = self.base_lon


NODES = [
    NodeProfile(1, "0x1a2b3c01", "Test Node 1", "TST1", "Heltec V3", 57.7089, 11.9746),
    NodeProfile(2, "0x1a2b3c02", "Test Node 2", "TST2", "Heltec V4", 57.7102, 11.9755),
    NodeProfile(3, "0x1a2b3c03", "Test Node 3", "TST3", "RAK4631",   57.7070, 11.9730),
]

TEXT_SAMPLES = [
    "Hello from {name}!",
    "Status check from {name}, all good.",
    "{name} reporting in.",
    "Anyone copy? This is {name}.",
    "Battery looking fine here ({name}).",
]

# Relative weights — position/telemetry fire more often than nodeinfo/text,
# similar to a real mesh.
KIND_WEIGHTS = {
    "position": 35,
    "telemetry_device": 20,
    "telemetry_environment": 20,
    "text_message": 15,
    "nodeinfo": 10,
}

# ── Packet building ──────────────────────────────────────────────────────────

_id_counter = itertools.count(int(time.time()) & 0xFFFFFFF)
_text_counter = 0


def _next_id() -> int:
    return next(_id_counter)


def _build_header(node: NodeProfile) -> dict:
    pid = _next_id()
    return {
        "to": "0xffffffff",
        "from": f"0x{node.from_int:08x}",
        "from_int": node.from_int,
        "id": pid,
        "id_hex": f"0x{pid:08x}",
        "hop_limit": 3,
        "want_ack": False,
        "via_mqtt": False,
        "hop_start": 3,
        "channel": "0x42",
    }


def _build_payload(kind: str, node: NodeProfile) -> dict:
    global _text_counter
    payload = dict(PAYLOAD_TEMPLATES[kind])  # copy, don't mutate the template

    if kind == "nodeinfo":
        payload.update({
            "node_id": node.node_id_hex,
            "long_name": node.long_name,
            "short_name": node.short_name,
            "hw_model": node.hw_model,
        })

    elif kind == "position":
        # Small random walk so the marker visibly drifts instead of jumping.
        node.lat += random.uniform(-0.0006, 0.0006)
        node.lon += random.uniform(-0.0006, 0.0006)
        payload.update({
            "latitude": round(node.lat, 6),
            "longitude": round(node.lon, 6),
            "altitude": node.base_alt + random.randint(-2, 2),
            "precision": 10,
            "gps_time": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
        })

    elif kind == "telemetry_device":
        node.battery = max(0.0, node.battery - random.uniform(0, 0.05))
        payload.update({
            "battery": round(node.battery, 1),
            "voltage": round(3.3 + (node.battery / 100) * 0.9, 3),
            "channel_util": round(random.uniform(2, 20), 1),
            "air_util_tx": round(random.uniform(1, 8), 1),
            "uptime_seconds": payload.get("uptime_seconds", 0) + random.randint(1, 30),
        })

    elif kind == "telemetry_environment":
        payload.update({
            "temperature": round(random.uniform(18, 26), 2),
            "humidity": round(random.uniform(40, 70), 1),
            "pressure": round(random.uniform(1005, 1020), 2),
            "iaq": random.randint(20, 80),
        })

    elif kind == "text_message":
        _text_counter += 1
        phrase = random.choice(TEXT_SAMPLES).format(name=node.short_name)
        payload["text"] = f"{phrase} [{_text_counter}]"

    return payload


def build_packet(kind: str, node: NodeProfile) -> DecodedMeshPacket:
    header = _build_header(node)
    payload = {**_PAYLOAD_DEFAULTS, **_build_payload(kind, node)}
    packet_dict = {**header, **payload, "was_encrypted": False}

    return DecodedMeshPacket(
        packet=packet_dict,
        raw_bytes=b"",
        node_id=header["from_int"],
        packet_type=payload.get("portnum", "UNKNOWN"),
    )

# ── Run loop ─────────────────────────────────────────────────────────────────


async def run(duration: int = 600, min_interval: float = 1.0, max_interval: float = 10.0):
    end_time = time.monotonic() + duration
    stats = Counter()

    print(
        f"[test_msg] running for {duration}s, "
        f"{min_interval}-{max_interval}s between packets, "
        f"nodes={[n.from_int for n in NODES]}"
    )

    # Seed each node with a nodeinfo packet so they exist before anything else.
    for node in NODES:
        pkt = build_packet("nodeinfo", node)
        await db_queue.put(pkt)
        await broadcast_queue.put(pkt)
        stats[("nodeinfo", node.from_int)] += 1
        print(f"[test_msg] seed nodeinfo node={node.from_int} ({node.short_name})")

    kinds, weights = zip(*KIND_WEIGHTS.items())

    try:
        while time.monotonic() < end_time:
            await asyncio.sleep(random.uniform(min_interval, max_interval))

            node = random.choice(NODES)
            kind = random.choices(kinds, weights=weights, k=1)[0]
            pkt = build_packet(kind, node)

            await db_queue.put(pkt)
            await broadcast_queue.put(pkt)
            stats[(kind, node.from_int)] += 1

            print(f"[test_msg] node={node.from_int} ({node.short_name}) -> {kind} id={pkt.packet['id']}")
    except asyncio.CancelledError:
        print("[test_msg] cancelled")
        raise
    finally:
        print("\n[test_msg] summary (kind, node) -> count — cross-check these against your DB:")
        for (kind, from_int), count in sorted(stats.items()):
            print(f"    {kind:<24} node={from_int}  {count}")
        print(f"[test_msg] total packets injected: {sum(stats.values())}")


def main():
    parser = argparse.ArgumentParser(description="Accelerated multi-node mesh test injector")
    parser.add_argument("--duration", type=int, default=900,
                         help="total run time in seconds (default 900 = 15 min)")
    parser.add_argument("--min-interval", type=float, default=1.0,
                         help="minimum seconds between packets (default 1)")
    parser.add_argument("--max-interval", type=float, default=10.0,
                         help="maximum seconds between packets (default 10)")
    args = parser.parse_args()

    asyncio.run(run(args.duration, args.min_interval, args.max_interval))


if __name__ == "__main__":
    main()
