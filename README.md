# sdrangel_meshtastic_dashboard_mkII# Meshtastic SDRangel Frontend (mkII)

**Goal**: Build a Python application that receives Meshtastic packets via UDP (from SDRangel), decodes them using the official meshtastic Python library, stores the data, and serves a real-time web interface.

## Tech Stack
- Python 3.11+
- Asyncio + `asyncio.Queue`
- FastAPI (with WebSockets)
- TinyDB
- Official `meshtastic` Python library (decoding only)
- Dataclasses (avoiding Pydantic for core models)
- Uvicorn

## Key Design Decisions
- Pure asyncio (no threads)
- Central queues for communication
- Reliable task wrapper that auto-restarts crashed tasks
- Clean separation of concerns
- WebSocket support for real-time updates

---

## Current Status (Updated: 2026-05-03)

**Phase 1: Foundation** → ✅ Completed  
**Phase 2: Web Layer** → In Progress (basic FastAPI running)

### Next Steps (Agreed Order)
1. Complete Phase 2: Basic FastAPI + **WebSocket** endpoint + improved homepage
2. Get UDP Listener running
3. Get Meshtastic Decoder running
4. Connect everything + update database
5. Build dynamic frontend pages

---

## How to Run

```bash
python -m src.meshtastic_frontend.main