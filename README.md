# sdrangel_meshtastic_dashboard_mkII# Meshtastic SDRangel Frontend (mkII)

**Goal**: Build a Python application that receives Meshtastic packets via UDP (from SDRangel), decodes them using the official meshtastic Python library, stores the data, and serves a real-time web interface.

## Tech Stack
- Python 3.11+
- Asyncio + `asyncio.Queue`
- FastAPI (with WebSockets)
- sqlalchemy
- Official `meshtastic` Python library (decoding only)
- Dataclasses (avoiding Pydantic for core models)
- Uvicorn

## Key Design Decisions
- Pure asyncio (no threads)
- Central queues for communication
- Reliable task wrapper that auto-restarts crashed tasks
- Clean separation of concerns
- WebSocket support for real-time updates

## Folder Structure
meshtastic-sdrangel-frontend/
├── src/
│   └── meshtastic_frontend/
│       ├── __init__.py
│       ├── main.py                 # Phase 1
│       ├── config.py               # Phase 1
│       ├── dataclasses.py          # Phase 1
│       ├── queues.py               # Phase 1
│       ├── task_manager.py         # Phase 1
│       ├── udp_listener.py         # Phase 3
│       ├── decoder.py              # Phase 3
│       ├── models.py               # Phase 4
│       ├── db_manager.py           # Phase 4
│       └── web/
│           ├── __init__.py
│           ├── app.py              # Phase 2
│           ├── routes.py
│           └── templates/
│               └── index.html      # Phase 5
├── tests/
├── pyproject.toml
├── requirements.txt
├── README.md
└── .env
---

## Current Status (Updated: 2026-05-09)

**Phase 1: Foundation** → Done
**Phase 2: FastAPI app** → Done
**Phase 3: UDP Listener & Mesh Decoder** → Done
**Phase 4: Database Manager** → Done

### Next Steps (Agreed Order)
1. Build dynamic frontend pages

---

## How to Run

```bash
python -m src.meshtastic_frontend.main