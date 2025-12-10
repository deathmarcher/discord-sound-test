import asyncio
import pytest

from discord_sound_test import bot


class FakeProc:
    def __init__(self, out: bytes = b"", returncode: int = 0):
        self._out = out
        self.returncode = returncode

    async def communicate(self, input=None):
        # simulate subprocess.communicate returning (stdout, stderr)
        return (self._out, b"")


@pytest.mark.asyncio
async def test_generate_tts_success(monkeypatch):
    async def fake_create_subprocess_exec(*args, **kwargs):
        return FakeProc(b"FAKEAUDIO", 0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    data = await bot.generate_tts_bytes("hello world")
    assert data == b"FAKEAUDIO"


@pytest.mark.asyncio
async def test_generate_tts_failure(monkeypatch):
    async def fake_create_subprocess_exec(*args, **kwargs):
        # return a process with empty output and non-zero returncode
        p = FakeProc(b"", 1)
        return p

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    data = await bot.generate_tts_bytes("hello")
    assert data == b""


@pytest.mark.asyncio
async def test_generate_tts_missing_executable(monkeypatch):
    async def fake_create_subprocess_exec(*args, **kwargs):
        raise FileNotFoundError()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    data = await bot.generate_tts_bytes("hello")
    assert data == b""


@pytest.mark.asyncio
async def test_probe_tts_true(monkeypatch):
    async def fake_create_subprocess_exec(*args, **kwargs):
        return FakeProc(b"OK", 0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    ok = await bot.probe_tts()
    assert ok is True


@pytest.mark.asyncio
async def test_probe_tts_false(monkeypatch):
    async def fake_create_subprocess_exec(*args, **kwargs):
        return FakeProc(b"", 1)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    ok = await bot.probe_tts()
    assert ok is False
