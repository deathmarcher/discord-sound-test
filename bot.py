#!/usr/bin/env python3
"""Discord Sound Test - prototype scaffold

This scaffold follows the project's DESIGN.md constraints:
- No environment variables; configuration is provided via `--config` JSON.
- Plays a configured join sound on join.
- Provides slash command stubs for `/join`, `/leave`, `/voicetest`, `/postvoicetestcommands`, and `/stop`.

Voice receive (capturing user audio) is library-dependent and non-trivial; the
`record_user_audio` function is a clear TODO where a suitable receive API
implementation should be added (or a maintained fork of discord.py used).

This file is intentionally minimal and safe: it demonstrates command flows
and playback using `ffmpeg` via `FFmpegPCMAudio`, but does not implement a
production-ready receive pipeline.
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import discord
from discord import FFmpegPCMAudio
from discord.ext import commands


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class VoiceTestBot(commands.Bot):
    def __init__(self, config: dict):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.config = config
        # Hard-coded join sound path per project policy (not stored in config)
        self.join_sound = "assets/join_sound.opus"
        # Temporary placeholder for voice-test playback until real capture is implemented
        self.placeholder_snippet = "assets/placeholder-voice-recording.opus"
        self.default_duration = config.get("default_duration", 5)
        self.max_duration = config.get("max_duration", 10)
        self.playback_delay = config.get("playback_delay", 1)
        self.rate_limits = config.get("rate_limits", {})

        # Runtime state: simple in-memory trackers
        self._active_recordings = {}  # guild_id -> user_id

    async def setup_hook(self) -> None:
        # Sync application command tree on startup
        await self.tree.sync()


bot: VoiceTestBot | None = None


async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")


async def ensure_voice_connected(interaction: discord.Interaction) -> discord.VoiceClient | None:
    # Ensure the bot is connected to the caller's voice channel
    user = interaction.user
    if not isinstance(user, discord.Member) or not user.voice or not user.voice.channel:
        await interaction.response.send_message("You must be in a voice channel for this command.", ephemeral=True)
        return None

    channel = user.voice.channel
    voice_client = interaction.guild.voice_client
    if voice_client and voice_client.channel.id == channel.id:
        return voice_client

    try:
        voice_client = await channel.connect()
    except Exception as exc:
        await interaction.response.send_message(f"Failed to join voice channel: {exc}", ephemeral=True)
        return None

    return voice_client


async def play_join_sound(voice_client: discord.VoiceClient):
    path = bot.join_sound if bot else None
    if not path:
        return
    if not os.path.exists(path):
        print(f"Join sound not found at {path}")
        return

    source = FFmpegPCMAudio(path)
    voice_client.play(source)
    # wait until playback completes
    while voice_client.is_playing():
        await asyncio.sleep(0.1)


async def record_user_audio(guild: discord.Guild, user: discord.User, duration: int) -> bytes:
    """
    TODO: Implement a proper voice receive pipeline.

    This function should capture only `user`'s audio for `duration` seconds and
    return raw PCM bytes (or Opus-encoded data) suitable for playback.

    Implementation notes:
    - discord.py stable releases historically do not provide a built-in high-level
      voice receive API. Consider using a maintained fork or a library that
      exposes per-user decoded PCM frames.
    - Alternative approach: use the low-level Opus packet receive hooks, decode
      to PCM and buffer into an in-memory BytesIO.

    For the scaffold, we raise NotImplementedError so Copilot or a developer can
    implement this with the chosen library.
    """
    raise NotImplementedError("record_user_audio must be implemented with a library that supports voice receive")


@staticmethod
def _ensure_duration(dur: int, default: int, maximum: int) -> int:
    if dur is None:
        return default
    try:
        d = int(dur)
    except Exception:
        return default
    if d <= 0:
        return default
    return min(d, maximum)


async def on_app_command_error(interaction: discord.Interaction, error: Exception):
    # Basic error handler for application commands
    try:
        await interaction.response.send_message(f"Error: {error}", ephemeral=True)
    except Exception:
        pass


def create_views():
    class VoiceTestView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=None)

        @discord.ui.button(label="Join", style=discord.ButtonStyle.primary)
        async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            vc = await ensure_voice_connected(interaction)
            if vc:
                await interaction.response.send_message("Joined voice channel.", ephemeral=True)
                await play_join_sound(vc)

        @discord.ui.button(label="Leave", style=discord.ButtonStyle.danger)
        async def leave_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            vc = interaction.guild.voice_client
            if vc:
                await vc.disconnect()
                await interaction.response.send_message("Left voice channel.", ephemeral=True)
            else:
                await interaction.response.send_message("Not connected.", ephemeral=True)

        @discord.ui.button(label="Test", style=discord.ButtonStyle.success)
        async def test_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            # Only allow pressing user to run test for themselves
            await interaction.response.send_message("Triggering voice test...", ephemeral=True)
            # Forward to the same flow as /voicetest
            # We call the slash command handler directly via the bot's tree
            try:
                # There is no public API to invoke app command handlers directly here;
                # rely on the user calling /voicetest or add specialized logic.
                await interaction.followup.send("Please use /voicetest to run the test (button scaffold).", ephemeral=True)
            except Exception:
                pass

    return VoiceTestView()


def main():
    parser = argparse.ArgumentParser(description="Discord Sound Test bot (prototype)")
    parser.add_argument("--config", required=True, help="Path to JSON config file (no env vars).")
    args = parser.parse_args()

    config_path = args.config
    if not os.path.exists(config_path):
        print(f"Config file not found: {config_path}")
        sys.exit(2)

    config = load_config(config_path)

    global bot
    bot = VoiceTestBot(config)

    @bot.event
    async def on_ready_event():
        print(f"Bot ready: {bot.user} ({bot.user.id})")

    @bot.tree.command(name="join")
    async def join_command(interaction: discord.Interaction):
        vc = await ensure_voice_connected(interaction)
        if not vc:
            return
        await interaction.response.send_message("Joined voice channel and playing join sound.", ephemeral=True)
        await play_join_sound(vc)

    @bot.tree.command(name="leave")
    async def leave_command(interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc:
            await vc.disconnect()
            await interaction.response.send_message("Left voice channel.", ephemeral=True)
        else:
            await interaction.response.send_message("Not connected.", ephemeral=True)

    @bot.tree.command(name="voicetest")
    async def voicetest_command(interaction: discord.Interaction, duration: int = None):
        # Enforce user-only trigger by design: interaction.user must be the target
        dur = _ensure_duration(duration, bot.default_duration, bot.max_duration)

        # Check membership and channel
        if not isinstance(interaction.user, discord.Member) or not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("You must be in a voice channel to run a voice test.", ephemeral=True)
            return

        guild_id = interaction.guild.id
        if bot._active_recordings.get(guild_id):
            await interaction.response.send_message("A recording is already in progress in this guild. Try again later.", ephemeral=True)
            return

        vc = await ensure_voice_connected(interaction)
        if not vc:
            return

        # Announce and play a short cue
        await interaction.response.send_message(f"Starting voice test for {dur}s. You will be recorded and then played back.", ephemeral=True)
        await interaction.channel.send(f"{interaction.user.display_name} is starting a voice test for {dur}s.")

        try:
            bot._active_recordings[guild_id] = interaction.user.id
            # TODO: integrate real capture here
            await interaction.channel.send("Recording (capture not implemented in scaffold).")
            # Simulate wait for recording duration
            await asyncio.sleep(dur)

            await interaction.channel.send("Recording complete. Waiting briefly before playback...")
            await asyncio.sleep(bot.playback_delay)

            # Playback placeholder: play a hard-coded placeholder snippet until real capture is implemented
            placeholder = bot.placeholder_snippet if bot else None
            if placeholder and os.path.exists(placeholder):
                vc.play(FFmpegPCMAudio(placeholder))
                await interaction.channel.send("Playing back placeholder snippet.")
                while vc.is_playing():
                    await asyncio.sleep(0.1)
            else:
                await interaction.channel.send("No placeholder snippet available to simulate playback.")

            await interaction.channel.send("Playback complete. Data discarded.")
        finally:
            bot._active_recordings.pop(guild_id, None)

    @bot.tree.command(name="postvoicetestcommands")
    async def post_commands(interaction: discord.Interaction):
        view = create_views()
        await interaction.response.send_message("Voice test controls:", view=view)

    @bot.tree.command(name="stop")
    async def stop_command(interaction: discord.Interaction):
        guild_id = interaction.guild.id
        current = bot._active_recordings.get(guild_id)
        if current and current == interaction.user.id:
            # No real recording in scaffold; just remove state
            bot._active_recordings.pop(guild_id, None)
            await interaction.response.send_message("Stopped your active recording.", ephemeral=True)
        else:
            await interaction.response.send_message("No active recording found for you.", ephemeral=True)

    # Basic startup checks
    if bot.join_sound and not Path(bot.join_sound).exists():
        print(f"Required join sound not found at: {bot.join_sound}")
        sys.exit(2)

    token = config.get("token")
    if not token:
        print("Config must include 'token' field. No env vars are used.")
        sys.exit(2)

    bot.run(token)


if __name__ == "__main__":
    main()
