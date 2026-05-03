import asyncio
import logging
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI

from .config import config
from .models import RawPacketEvent, DecodedMeshPacket, AppEvent
from .queues import raw_packet_queue, decoded_packet_queue, broadcast_queue


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=getattr(logging, config.log_level),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    
    logger.info("🚀 Starting Meshtastic SDRangel Frontend...")
    logger.info(f"Listening for UDP on {config.udp_host}:{config.udp_port}")
    logger.info(f"Web UI will be available at http://localhost:{config.api_port}")

    # TODO: Start background tasks later
    tasks = []

    try:
        yield
    finally:
        logger.info("Shutting down...")


# Simple placeholder app for now
def create_app() -> FastAPI:
    app = FastAPI(title="Meshtastic SDRangel Frontend", lifespan=lifespan)
    
    @app.get("/")
    async def root():
        return {
            "message": "Meshtastic SDRangel Frontend is running!",
            "status": "ok"
        }
    
    return app


async def main():
    """Entry point with better shutdown handling"""
    app = create_app()
    
    config_uv = uvicorn.Config(
        app, 
        host=config.api_host, 
        port=config.api_port, 
        log_level="info",
        timeout_keep_alive=0
    )
    server = uvicorn.Server(config_uv)
    
    try:
        await server.serve()
    except asyncio.CancelledError:
        logger.info("Shutdown requested...")
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Shutting down gracefully...")
    finally:
        # Give tasks time to clean up
        await asyncio.sleep(0.1)
        logger.info("Server stopped.")


if __name__ == "__main__":
    asyncio.run(main())