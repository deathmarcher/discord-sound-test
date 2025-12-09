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
import time
import traceback
import subprocess
import functools
import inspect
import logging

# Configure module logger early so decorator and functions can use it
logger = logging.getLogger("discord_sound_test")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setLevel(logging.DEBUG)
    fmt = logging.Formatter("aaaa [%(levelname)s:%(name)s] %(asctime)s %(message)s", "%Y-%m-%d %H:%M:%S")
    handler.setFormatter(fmt)
    logger.addHandler(handler)
    # Keep discord library logs reasonable
    logging.getLogger("discord").setLevel(logging.INFO)



# Directory to save debug snippets. These are kept until you remove them.
DEBUG_SNIPPETS_DIR = "debug_snippets"

# log_call decorator: logs entry/args/exceptions when its debug target is enabled
def log_call(target: str):
    """Decorator to log function entry/args to the bot debug system for `target`.

    It works for both sync and async functions. Logging is performed at call
    time so `bot` can be set after module import.
    """
    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                if bot and getattr(bot, "debug", None) and bot.debug_enabled(target):
                    try:
                        bot.debug(target, f"CALL {func.__name__} args={args} kwargs={kwargs}")
                    except Exception:
                        logger.warning(f"[DEBUG:{target}] failed to format args for {func.__name__}")
                return await func(*args, **kwargs)
            except Exception:
                # Log exception details
                if bot and getattr(bot, "debug", None) and bot.debug_enabled(target):
                    bot.debug(target, f"EXCEPTION in {func.__name__}: {traceback.format_exc()}")
                raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                if bot and getattr(bot, "debug", None) and bot.debug_enabled(target):
                    try:
                        bot.debug(target, f"CALL {func.__name__} args={args} kwargs={kwargs}")
                    except Exception:
                        logger.warning(f"[DEBUG:{target}] failed to format args for {func.__name__}")
                return func(*args, **kwargs)
            except Exception:
                if bot and getattr(bot, "debug", None) and bot.debug_enabled(target):
                    bot.debug(target, f"EXCEPTION in {func.__name__}: {traceback.format_exc()}")
                raise

        return async_wrapper if inspect.iscoroutinefunction(func) else sync_wrapper

    return decorator


@log_call("storage")
def save_debug_snippet(data: bytes, guild: discord.Guild, user: discord.User) -> str:
    """Write captured audio bytes to a debug file and return the path.

    This function is intentionally separate so it can be removed or disabled
    easily after debugging. Files are written under `debug_snippets/`.
    """
    os.makedirs(DEBUG_SNIPPETS_DIR, exist_ok=True)
    ts = int(time.time())
    filename = f"snippet_g{guild.id}_u{user.id}_{ts}.ogg"
    path = os.path.join(DEBUG_SNIPPETS_DIR, filename)
    with open(path, "wb") as f:
        f.write(data)
    return path


@log_call("playback")
def probe_media(path: str) -> tuple[bool, str]:
    """Run ffmpeg to probe the media file and return (ok, combined_output).

    This runs `ffmpeg -v info -i <path> -f null -` and captures stderr/stdout
    which ffmpeg prints to stderr. Returns True if ffmpeg exit code == 0.
    """
    try:
        # ffmpeg prints info to stderr by default
        proc = subprocess.run(["ffmpeg", "-v", "info", "-i", path, "-f", "null", "-"], capture_output=True, text=True, timeout=10)
        out = proc.stdout + "\n" + proc.stderr
        return (proc.returncode == 0, out)
    except Exception as exc:
        return (False, f"ffmpeg probe failed: {exc} \n{traceback.format_exc()}")

# Static list of debug targets. Use these names with --debug or with individual
# flags like --debug-voice, --debug-sinks, etc.
DEBUG_TARGETS = [
    "sinks",
    "voice",
    "playback",
    "commands",
    "config",
    "rate_limit",
    "storage",
]


def redact_config(cfg: dict) -> dict:
    """Return a shallow copy of the config suitable for logging without the token."""
    if not isinstance(cfg, dict):
        return cfg
    out = dict(cfg)
    if "token" in out:
        out["token"] = "<redacted>"
    return out




def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class RateLimitHandler:
    def __init__(self):
        self.last_connect_time = 0
        self.min_interval = 2.0  # Minimum seconds between connection attempts

    async def wait_if_needed(self):
        now = time.time()
        elapsed = now - self.last_connect_time
        if elapsed < self.min_interval:
            wait_time = self.min_interval - elapsed
            logger.info(f"Rate limit: waiting {wait_time:.2f}s before connecting")
            await asyncio.sleep(wait_time)
        self.last_connect_time = time.time()

rate_limiter = RateLimitHandler()


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

        # runtime debug targets (set by CLI args)
        self.debug_targets: set[str] = set()

    def set_debug_targets(self, targets: set):
        self.debug_targets = set(targets or [])

    def debug_enabled(self, target: str) -> bool:
        return target in getattr(self, "debug_targets", set())

    def debug(self, target: str, msg: str):
        if self.debug_enabled(target):
            # Route debug through the module logger so stdout/stderr capture works
            logger.debug(f"[{target}] {msg}")

    # py-cord syncs commands automatically, no setup_hook needed for tree sync


bot: VoiceTestBot | None = None


async def on_ready():
    logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")


@log_call("voice")
async def ensure_voice_connected(ctx: discord.ApplicationContext | discord.Interaction) -> discord.VoiceClient | None:
    # Ensure the bot is connected to the caller's voice channel
    user = getattr(ctx, "author", None) or getattr(ctx, "user", None)
    if not isinstance(user, discord.Member) or not user.voice or not user.voice.channel:
        respond = getattr(ctx, "respond", None)
        if not respond and hasattr(ctx, "response"):
             respond = ctx.response.send_message
        if respond:
            await respond("You must be in a voice channel for this command.", ephemeral=True)
        return None

    channel = user.voice.channel
    voice_client = ctx.guild.voice_client
    if voice_client and voice_client.channel.id == channel.id:
        return voice_client

    try:
        if bot and bot.debug_enabled("voice"):
            bot.debug("voice", f"Attempting to connect to voice channel id={channel.id} in guild={ctx.guild.id}")
        
        await rate_limiter.wait_if_needed()
        voice_client = await channel.connect()
    except Exception as exc:
        respond = getattr(ctx, "respond", None)
        if not respond and hasattr(ctx, "response"):
             respond = ctx.response.send_message
        if respond:
            await respond(f"Failed to join voice channel: {exc}", ephemeral=True)
        return None

    return voice_client


@log_call("playback")
async def play_join_sound(voice_client: discord.VoiceClient):
    path = bot.join_sound if bot else None
    if not path:
        return
    if not os.path.exists(path):
        logger.warning(f"Join sound not found at {path}")
        return

    if bot and bot.debug_enabled("playback"):
        bot.debug("playback", f"Playing join sound from {path}")
        # Probe the file with ffmpeg to show codec/format info for debugging
        ok, out = probe_media(path)
        bot.debug("playback", f"ffmpeg probe ok={ok} output:\n{out}")
    source = FFmpegPCMAudio(path)
    voice_client.play(source)
    # wait until playback completes
    while voice_client.is_playing():
        await asyncio.sleep(0.1)


@log_call("sinks")
async def record_user_audio(guild: discord.Guild, user: discord.User, duration: int) -> bytes:
    """
    Capture `user`'s audio for `duration` seconds using py-cord's native voice receive.
    Returns raw OGG bytes (Opus encoded).
    """
    vc: discord.VoiceClient = guild.voice_client
    if not vc:
        raise RuntimeError("Bot is not connected to a voice channel in this guild")

    if bot and bot.debug_enabled("sinks"):
        bot.debug("sinks", f"Using py-cord native OGGSink")

    sink = discord.sinks.OGGSink()

    async def finished_callback(sink, *args):
        pass

    # Start recording
    try:
        # Note: Opus decoding errors in logs are common with UDP voice traffic and can often be ignored
        # if the resulting audio is intelligible.
        vc.start_recording(sink, finished_callback)
        if bot and bot.debug_enabled("sinks"):
            bot.debug("sinks", f"Started recording for duration={duration}s on guild={guild.id}")
    except Exception as exc:
        if bot and bot.debug_enabled("sinks"):
            bot.debug("sinks", f"start_recording threw: {exc}\n{traceback.format_exc()}")
        raise RuntimeError("Failed to start recording on VoiceClient") from exc

    # Wait for the requested duration
    await asyncio.sleep(duration)

    # Stop recording
    try:
        vc.stop_recording()
    except Exception:
        pass

    # Small delay to allow sink to flush
    await asyncio.sleep(0.2)

    # Extract audio
    # py-cord's OGGSink stores data in sink.audio_data[user_id] which is an AudioData object
    # AudioData.file is a BytesIO object
    try:
        # sink.audio_data is a dict of user_id -> AudioData
        # user_id is int
        audio_data = sink.audio_data.get(user.id)
        if not audio_data:
             # Try string key just in case
             audio_data = sink.audio_data.get(str(user.id))
        
        if not audio_data:
             # If user didn't speak, we might not have data.
             # Check if we have ANY data to debug
             if bot and bot.debug_enabled("sinks"):
                 bot.debug("sinks", f"No audio data for user {user.id}. Available keys: {list(sink.audio_data.keys())}")
             raise RuntimeError(f"No audio recorded for user {user.id}")

        # AudioData.file is the BytesIO
        audio_bytes = audio_data.file.getvalue()
        return audio_bytes

    except Exception as exc:
        if bot and bot.debug_enabled("sinks"):
             bot.debug("sinks", f"Error extracting audio: {exc}")
        raise


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
    parser.add_argument("--debug", action="append", choices=DEBUG_TARGETS, help="Enable debugging for a target (can be passed multiple times).")
    parser.add_argument("--debug-all", action="store_true", help="Enable all debug targets.")
    # individual debug flags for convenience
    for t in DEBUG_TARGETS:
        parser.add_argument(f"--debug-{t.replace('_', '-')}", action="store_true", help=f"Enable debug target: {t}")
    args = parser.parse_args()

    config_path = args.config
    if not os.path.exists(config_path):
        logger.error(f"Config file not found: {config_path}")
        sys.exit(2)

    config = load_config(config_path)

    global bot
    bot = VoiceTestBot(config)

    # Configure debug targets on the bot
    selected: set[str] = set()
    if getattr(args, "debug_all", False):
        selected = set(DEBUG_TARGETS)
    if getattr(args, "debug", None):
        selected.update(args.debug)
    for t in DEBUG_TARGETS:
        flag_name = f"debug_{t.replace('-', '_')}"
        if getattr(args, flag_name, False):
            selected.add(t)
    bot.set_debug_targets(selected)
    bot.debug("config", f"Debug targets: {sorted(list(selected))}")
    bot.debug("config", f"Loaded config: {redact_config(config)}")
    logger.debug("startup completed preliminary setup")

    @bot.event
    async def on_ready_event():
        logger.info(f"Bot ready: {bot.user} ({bot.user.id})")

    @bot.slash_command(name="join")
    async def join_command(ctx: discord.ApplicationContext):
        if bot and bot.debug_enabled("commands"):
            bot.debug("commands", f"/join invoked by user={ctx.author.id} in guild={ctx.guild.id}")
        vc = await ensure_voice_connected(ctx)
        if not vc:
            return
        await ctx.respond("Joined voice channel and playing join sound.", ephemeral=True)
        await play_join_sound(vc)

    @bot.slash_command(name="leave")
    async def leave_command(ctx: discord.ApplicationContext):
        vc = ctx.guild.voice_client
        if vc:
            await vc.disconnect()
            await ctx.respond("Left voice channel.", ephemeral=True)
        else:
            await ctx.respond("Not connected.", ephemeral=True)

    @bot.slash_command(name="voicetest")
    async def voicetest_command(ctx: discord.ApplicationContext, duration: int = None):
        if bot and bot.debug_enabled("commands"):
            bot.debug("commands", f"/voicetest invoked by user={ctx.author.id} duration={duration}")
        # Enforce user-only trigger by design: ctx.author must be the target
        dur = _ensure_duration(duration, bot.default_duration, bot.max_duration)

        # Check membership and channel
        if not isinstance(ctx.author, discord.Member) or not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.respond("You must be in a voice channel to run a voice test.", ephemeral=True)
            return

        guild_id = ctx.guild.id
        if bot._active_recordings.get(guild_id):
            await ctx.respond("A recording is already in progress in this guild. Try again later.", ephemeral=True)
            return

        vc = await ensure_voice_connected(ctx)
        if not vc:
            return

        # Announce and play a short cue
        await ctx.respond(f"Starting voice test for {dur}s. You will be recorded and then played back.", ephemeral=True)
        await ctx.channel.send(f"{ctx.author.display_name} is starting a voice test for {dur}s.")

        try:
            bot._active_recordings[guild_id] = ctx.author.id
            # Attempt live record via sinks; record_user_audio will raise if not supported
            try:
                if bot and bot.debug_enabled("commands"):
                    bot.debug("commands", f"Starting live capture for user={ctx.author.id} dur={dur}")
                audio_bytes = await record_user_audio(ctx.guild, ctx.author, dur)

                # Save for debugging (separate function for easy removal later)
                snippet_path = save_debug_snippet(audio_bytes, ctx.guild, ctx.author)
                if bot and bot.debug_enabled("storage"):
                    bot.debug("storage", f"Saved debug snippet to {snippet_path}")

                await ctx.channel.send("Recording complete. Waiting briefly before playback...")
                await asyncio.sleep(bot.playback_delay)

                # Playback the saved file
                vc.play(FFmpegPCMAudio(snippet_path))
                await ctx.channel.send(f"Playing back recorded snippet from `{snippet_path}`.")
                while vc.is_playing():
                    await asyncio.sleep(0.1)

                await ctx.channel.send("Playback complete. Debug file retained for inspection.")
            except Exception as exc:
                # If recording isn't supported or errors, fall back to placeholder snippet
                if bot and bot.debug_enabled("sinks"):
                    bot.debug("sinks", f"record_user_audio failed: {exc}")
                placeholder = bot.placeholder_snippet if bot else None
                if placeholder and os.path.exists(placeholder):
                    vc.play(FFmpegPCMAudio(placeholder))
                    await ctx.channel.send("Recording failed; playing placeholder snippet instead.")
                    while vc.is_playing():
                        await asyncio.sleep(0.1)
                else:
                    await ctx.channel.send(f"Recording failed and no placeholder available: {exc}")
        finally:
            bot._active_recordings.pop(guild_id, None)

    @bot.slash_command(name="postvoicetestcommands")
    async def post_commands(ctx: discord.ApplicationContext):
        view = create_views()
        await ctx.respond("Voice test controls:", view=view)

    @bot.slash_command(name="stop")
    async def stop_command(ctx: discord.ApplicationContext):
        guild_id = ctx.guild.id
        current = bot._active_recordings.get(guild_id)
        if current and current == ctx.author.id:
            # No real recording in scaffold; just remove state
            bot._active_recordings.pop(guild_id, None)
            await ctx.respond("Stopped your active recording.", ephemeral=True)
        else:
            await ctx.respond("No active recording found for you.", ephemeral=True)

    # Basic startup checks
    if bot.join_sound and not Path(bot.join_sound).exists():
        logger.error(f"Required join sound not found at: {bot.join_sound}")
        sys.exit(2)

    token = config.get("token")
    if not token:
        logger.error("Config must include 'token' field. No env vars are used.")
        sys.exit(2)

    bot.run(token)


if __name__ == "__main__":
    main()
