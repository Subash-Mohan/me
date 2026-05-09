import asyncio
from typing import Any


class Emitter:
    """Push packets onto the per-request SSE outbound queue. Thread-safe."""

    def __init__(self, queue: asyncio.Queue[Any], loop: asyncio.AbstractEventLoop) -> None:
        self._queue = queue
        self._loop = loop

    def emit(self, packet: Any) -> None:
        self._loop.call_soon_threadsafe(self._queue.put_nowait, packet)
