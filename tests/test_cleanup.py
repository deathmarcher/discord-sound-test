import asyncio
from types import SimpleNamespace

import pytest

import bot as botmod


class DummyVC:
    def __init__(self):
        self.stop_called = False
        self.disconnected = False

    def stop_recording(self):
        self.stop_called = True

    async def disconnect(self):
        # simulate async disconnect
        await asyncio.sleep(0)
        self.disconnected = True


class DummyGuild:
    def __init__(self, gid, vc):
        self.id = gid
        self.voice_client = vc


@pytest.mark.asyncio
async def test_cleanup_and_shutdown_stops_and_clears():
    bot_obj = SimpleNamespace()
    vc = DummyVC()
    guild = DummyGuild(42, vc)
    bot_obj.guilds = [guild]
    bot_obj._active_recordings = {42: 12345}

    closed = False

    async def _close():
        nonlocal closed
        closed = True

    bot_obj.close = _close

    # Run the cleanup routine
    await botmod.cleanup_and_shutdown(bot_obj, sig_name="TEST")

    assert vc.stop_called, "Expected stop_recording to be called"
    assert vc.disconnected, "Expected disconnect to be awaited"
    assert bot_obj._active_recordings == {}, "Expected active recordings to be cleared"
    assert closed, "Expected bot.close to be awaited"
