# Meshtastic SDRangel Frontend (mkII)

## 🎯 Goal
Build a Python application that receives Meshtastic packets via UDP (from SDRangel), decodes them using the official meshtastic Python library, stores the data, and serves a real-time web interface.

## 🧰 Tech Stack
- Python 3.11+
- Asyncio + `asyncio.Queue`
- FastAPI (with WebSockets)
- SQLAlchemy with aiosqllet
- Official `meshtastic` Python library (decoding only)
- Pydantic for validation
- Jinja2 for templating
- Uvicorn ASGI server

## 🧠 Key Design Decisions
- Pure asyncio (no threads)
- Central queues for communication
- Reliable task wrapper that auto-restarts crashed tasks
- Clean separation of concerns
- WebSocket support for real-time updates

## 📦 Installation

1. Ensure you have Python 3.11+ installed.
2. Clone the repository and navigate to the project directory.
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
   Or if using uv:
   ```bash
   uv sync
   ```
- Clean separation of concerns
- WebSocket support for real-time updates

## Installation

1. Ensure you have Python 3.11+ installed.
2. Clone the repository and navigate to the project directory.
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
   Or if using uv:
   ```bash
   uv sync
   ```

## Folder Structure
```
meshtastic-sdrangel-frontend/
├── src/
│   └── meshtastic_frontend/
│       ├── __init__.py
│       ├── main.py                 # Main entry point
│       ├── config.py               # Configuration management
│       ├── models.py               # Data models
│       ├── queues.py               # Async queues
│       ├── task_manager.py         # Task management
│       ├── udp_listener.py         # UDP packet listener
│       ├── decoder.py              # Meshtastic packet decoder
│       ├── db_manager.py           # Database operations
│       └── web/
│           ├── __init__.py
│           ├── app.py              # FastAPI application
│           ├── routes.py           # API routes
│           ├── static/
│           │   └── test.html       # Test page
│           └── templates/
│               └── index.html      # Main dashboard template
├── tests/
├── data/                           # Data storage
├── pyproject.toml                  # Project configuration
├── requirements.txt                # Python dependencies
├── start.py                        # Alternative entry point
├── README.md
├── LICENSE
└── .env                            # Environment variables
```

## How to Run

### Using the main module:
```bash
python -m src.meshtastic_frontend.main
```

### Using the start script:
```bash
python start.py
```

The application will start the FastAPI server on the configured host and port (default: http://localhost:8000).

## Configuration

Create a `.env` file in the root directory with your configuration settings. See `config.py` for available options.

## Development

For development dependencies:
```bash
pip install -e .[dev]
```
Or with uv:
```bash
uv sync --dev
```

Run tests:
```bash
pytest
```

Lint code:
```bash
ruff check .
black .
```

## API Endpoints

- `GET /` - Main dashboard
- `GET /ws` - WebSocket endpoint for real-time updates
- Additional endpoints defined in `routes.py`

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and linting
5. Submit a pull request

## License

See LICENSE file for details.
