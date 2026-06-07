# File: test_module.py
"""
File Description: This file contains the implementation of a test module that places test messages on the broadcast queue when config.test_state is true.
"""

import asyncio
from .config import config
from .queues import broadcast_queue
from .models import AppEvent

async def enqueue_test_messages():
    """
    Enqueue test messages on the broadcast queue if config.test_state is true.
    """
    while True:
        if config.test_state:
            # Create a test message
            test_message = AppEvent(event_type="new_message", 
                                    payload={
                                        "timestamp": "00:00:00",
                                        "from_node": f"0x12345678",
                                        "text": "the test message",
                                        "channel": "test",
                                    }
                                    )
            
            # Enqueue the test message
            await broadcast_queue.put(test_message)
        
        # Wait for some time before checking again
        await asyncio.sleep(10)  # You can adjust this interval as needed

# Example usage in main.py if you want to run it separately from the main application
if __name__ == "__main__":
    import asyncio
    asyncio.run(enqueue_test_messages())
