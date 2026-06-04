"""
File description: This file contains the main entry point for the Meshtatic SDRangel Frontend.
"""
import asyncio
import logging
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI

from .config import config
from .task_manager import reliable_task
from .web.app import create_app as create_web_app

# Import tasks
from .udp_listener import udp_listener_task
from .decoder import decoder_task
from .db_manager import db_manager_task
from .broadcaster import broadcaster_task

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan handler for the FastAPI application
    """
    logging.basicConfig(
        level=getattr(logging, config.log_level),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    
    logger.info("Starting Meshtastic SDRangel Frontend...")

    # Start background tasks
    tasks = [
        asyncio.create_task(reliable_task(udp_listener_task, "UDP Listener", restart_delay=2.0)),
        asyncio.create_task(reliable_task(decoder_task, "Meshtastic Decoder", restart_delay=2.0)),
        asyncio.create_task(reliable_task(db_manager_task, "Database Manager", restart_delay=2.0)),
        asyncio.create_task(reliable_task(broadcaster_task, "Broadcaster", restart_delay=2.0)),
    ]

    logger.info("Background tasks started")

    app.state.background_tasks = tasks
    
    try:
        yield
    finally:
        logger.info("Shutting down background tasks...")
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("All tasks stopped.")

def create_app() -> FastAPI:
    """Create the FastAPI application
    """
    app = create_web_app(lifespan=lifespan)
    return app

async def main():
    """Entry point
    """
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
        logger.info("Keyboard interrupt received...")
    finally:
        logger.info("Server stopped.")

if __name__ == "__main__":
    asyncio.run(main())