from types import SimpleNamespace

import pytest

import bot as botmod


@pytest.mark.asyncio
async def test_run_voice_test_aborts_when_tts_unavailable(monkeypatch):
    """If TTS generation returns empty bytes, run_voice_test should abort
    before recording and notify the user about audible-consent."""

    # Make generate_tts_bytes return empty bytes to simulate missing TTS
    async def fake_generate_tts(text: str) -> bytes:
        return b""

    monkeypatch.setattr(botmod, "generate_tts_bytes", fake_generate_tts)

    # Fake ensure_voice_connected to avoid real network/voice operations
    class DummyVC:
        def play(self, source):
            pass

        def is_playing(self):
            return False

    async def fake_ensure(ctx):
        return DummyVC()

    monkeypatch.setattr(botmod, "ensure_voice_connected", fake_ensure)

    # Replace discord.Member with a simple local class so isinstance checks pass
    class DummyMember:
        def __init__(self):
            self.display_name = "Tester"
            self.id = 123
            self.voice = SimpleNamespace(channel=True)

    monkeypatch.setattr(botmod.discord, "Member", DummyMember)

    # Capture messages sent via interaction.respond and channel.send
    sent = {}

    class DummyChannel:
        async def send(self, msg):
            sent.setdefault("channel", []).append(msg)

    class DummyInteraction:
        def __init__(self):
            self.guild = SimpleNamespace(id=1)
            self.user = DummyMember()
            self.channel = DummyChannel()

        async def respond(self, msg, ephemeral=True):
            sent.setdefault("respond", []).append(msg)

    inter = DummyInteraction()

    # Ensure module-level `bot` exists with minimal attributes used by run_voice_test
    botmod.bot = SimpleNamespace(
        _active_recordings={},
        default_duration=1,
        playback_delay=0,
        debug_enabled=lambda _t: False,
        debug=lambda _t, _m: None,
    )

    # Run the voice test; it should abort at the TTS gating step
    await botmod.run_voice_test(inter, inter.user, 1)

    # Assert that we informed the user that TTS was unavailable
    resp_msgs = sent.get("respond", [])
    chan_msgs = sent.get("channel", [])
    combined = " ".join(resp_msgs + chan_msgs)
    assert (
        "Voice announcement unavailable" in combined or "Voice test aborted" in combined
    ), f"Expected abort message in {combined!r}"
