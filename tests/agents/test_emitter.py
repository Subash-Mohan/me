import asyncio
import threading

import pytest

from app.agents.emitter import Emitter
from app.agents.packets import TextDeltaPacket


@pytest.mark.asyncio
async def test_emit_from_loop_thread():
    queue: asyncio.Queue = asyncio.Queue()
    emitter = Emitter(queue, asyncio.get_running_loop())
    emitter.emit(TextDeltaPacket(delta="x"))
    pkt = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert pkt.delta == "x"


@pytest.mark.asyncio
async def test_emit_from_worker_thread():
    queue: asyncio.Queue = asyncio.Queue()
    emitter = Emitter(queue, asyncio.get_running_loop())

    def worker():
        emitter.emit(TextDeltaPacket(delta="from-thread"))

    threading.Thread(target=worker).start()
    pkt = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert pkt.delta == "from-thread"
