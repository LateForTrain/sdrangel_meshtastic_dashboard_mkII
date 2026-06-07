"""This module monitors tasks and automatically restarting them if they crashes due to any exceptions (excluding being cancelled explicitly). 
"""
import asyncio
import logging
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)

async def reliable_task(
    coro_func: Callable[[], Awaitable[None]],
    task_name: str,
    restart_delay: float = 1.0,
    max_restarts: int = 10
):
    """
    Wrapper that auto-restarts crashed tasks
    
    Args:
        coro_func (Callable[[], Awaitable[]]): The coroutine function to be executed.
        task_name (str): The name of the task.
        restart_delay (float, optional): The delay in seconds between restarts. Defaults to 1.0 seconds.
        max_restarts (int, optional): The maximum number of restarts. Defaults to 10.
    """
    restarts = 0
    while restarts < max_restarts:
        try:
            logger.info(f"Starting task: {task_name}")
            await coro_func()
            logger.warning(f"Task {task_name} exited normally")
            break
        except asyncio.CancelledError:
            logger.info(f"Task {task_name} cancelled")
            break
        except Exception as e:
            restarts += 1
            logger.error(f"Task {task_name} crashed (attempt {restarts}/{max_restarts}): {e}", exc_info=True)
            if restarts < max_restarts:
                await asyncio.sleep(restart_delay)
            else:
                logger.critical(f"Task {task_name} failed permanently after {max_restarts} attempts")
                raise