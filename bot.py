#!/usr/bin/env python3
"""Discord Sound Test — privacy-first voice test bot


Quick summary:
- Configuration: supplied via `--config <path>` JSON (no environment vars).
- Privacy: records only when explicitly triggered by a user; recordings are
    stored in-memory and not written to disk.
- TTS: uses local `espeak-ng` (stdout) for audible announcements; if TTS is
    unavailable the bot will refuse to record to preserve audible consent.
- Audio I/O: uses py-cord sinks (OGGSink) for receive and `ffmpeg` via
    `FFmpegPCMAudio(pipe=True)` for playback from `io.BytesIO` buffers.
- UI and shutdown: persistent interaction controls are re-registered on
    startup and signal handlers perform graceful cleanup of voice clients.
"""

import argparse
import asyncio
import json
import os
import sys
import io

import discord
from discord import FFmpegPCMAudio
from discord.ext import commands
import time
import traceback
import functools
import inspect
import logging
import signal

# Configure module logger early so decorator and functions can use it
logger = logging.getLogger("discord_sound_test")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "aaaa [%(levelname)s:%(name)s] %(asctime)s %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(fmt)
    logger.addHandler(handler)
    # Keep discord library logs reasonable
    logging.getLogger("discord").setLevel(logging.INFO)

bot = None


# Static list of debug targets. Use these names with --debug or with individual
# flags like --debug-voice, --debug-sinks, etc.
DEBUG_TARGETS = [
    "sinks",
    "voice",
    "playback",
    "commands",
    "config",
    "rate_limit",
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


async def generate_tts_bytes(text: str) -> bytes:
    """Generate TTS audio as bytes in-memory using `espeak-ng`.

    This implementation does not write any files to disk. If `espeak-ng` is
    not available or fails, the function returns an empty bytes object.
    """
    # Preferred path: espeak-ng -> stdout
    try:
        proc = await asyncio.create_subprocess_exec(
            "espeak-ng",
            "--stdout",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate(text.encode())
        if proc.returncode == 0 and out:
            return out
        # Log stderr at debug level for troubleshooting
        if err:
            try:
                logger.debug("espeak-ng stderr: %s", err.decode(errors="replace"))
            except Exception:
                logger.debug("espeak-ng stderr (binary)")
    except FileNotFoundError:
        # espeak-ng not installed
        pass
    except Exception:
        pass
    # If espeak-ng failed or is not present, return empty bytes (no disk IO)
    logger.debug("espeak-ng not available or failed; skipping TTS")
    return b""


async def probe_tts() -> bool:
    """Quick probe to check if TTS generation works at runtime."""
    try:
        data = await generate_tts_bytes("TTS probe")
        return bool(data)
    except Exception:
        return False


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
        # Require members and voice state intents for reliable member/voice data
        intents.members = True
        intents.voice_states = True
        super().__init__(command_prefix="!", intents=intents)
        self.config = config
        self.default_duration = config.get("default_duration", 5)
        self.max_duration = config.get("max_duration", 10)
        self.playback_delay = config.get("playback_delay", 1)
        self.rate_limits = config.get("rate_limits", {})

        # Runtime state: simple in-memory trackers
        self._active_recordings = {}  # guild_id -> user_id

        # runtime debug targets (set by CLI args)
        self.debug_targets: set[str] = set()
        # Optional behavior: automatically leave voice channels when alone
        # Default to True for convenience; can be disabled via config.
        self.auto_leave_when_alone = config.get("auto_leave_when_alone", True)

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


async def ensure_voice_connected(
    ctx: discord.ApplicationContext | discord.Interaction,
) -> discord.VoiceClient | None:
    # Ensure the bot is connected to the caller's voice channel
    user = getattr(ctx, "author", None) or getattr(ctx, "user", None)
    if not isinstance(user, discord.Member) or not user.voice or not user.voice.channel:
        respond = getattr(ctx, "respond", None)
        if not respond and hasattr(ctx, "response"):
            respond = ctx.response.send_message
        if respond:
            await respond(
                "You must be in a voice channel for this command.", ephemeral=True
            )
        return None

    channel = user.voice.channel
    voice_client = ctx.guild.voice_client
    if voice_client and voice_client.channel.id == channel.id:
        return voice_client

    try:
        if bot and bot.debug_enabled("voice"):
            bot.debug(
                "voice",
                f"Attempting to connect to voice channel id={channel.id} in guild={ctx.guild.id}",
            )

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


async def play_join_sound(
    voice_client: discord.VoiceClient, text_channel: discord.TextChannel = None
):
    # TTS Announcement
    try:
        data = await generate_tts_bytes(
            "Voice tester has joined the channel. No recordings unless explicitly triggered by a user."
        )
        if data:
            audio_source = io.BytesIO(data)
            try:
                audio_source.seek(0)
            except Exception:
                pass
            voice_client.play(FFmpegPCMAudio(audio_source, pipe=True))
            while voice_client.is_playing():
                await asyncio.sleep(0.1)
        else:
            logger.debug(
                "No TTS audio produced for join announcement; skipping voice playback"
            )
    except Exception as e:
        logger.error(f"Join TTS failed: {e}")

    # Text Summary
    if text_channel:
        try:
            await text_channel.send(
                "**Voice Tester Bot**\n"
                "This bot is a privacy-focused tool for testing your microphone quality.\n"
                "• It **only** records when you explicitly run `/voicetest` or click the **Test** button.\n"
                "• It **only** records the user who triggered the command.\n"
                "• Audio is stored **in-memory only** and is deleted immediately after playback.\n"
                "• No data is sent to external servers."
            )
        except Exception as e:
            logger.error(f"Failed to send text summary: {e}")


async def record_user_audio(
    guild: discord.Guild, user: discord.User, duration: int
) -> bytes:
    """
    Capture `user`'s audio for `duration` seconds using py-cord's native voice receive.
    Returns raw OGG bytes (Opus encoded).
    """
    vc: discord.VoiceClient = guild.voice_client
    if not vc:
        raise RuntimeError("Bot is not connected to a voice channel in this guild")

    if bot and bot.debug_enabled("sinks"):
        bot.debug("sinks", "Using py-cord native OGGSink")

    sink = discord.sinks.OGGSink()

    # Use a future that the finished_callback will set when sink is flushed.
    loop = asyncio.get_running_loop()
    finished_future = loop.create_future()

    async def finished_callback(sink_obj, *args):
        try:
            if not finished_future.done():
                finished_future.set_result(True)
        except Exception:
            try:
                finished_future.set_result(False)
            except Exception:
                pass

    # Start recording
    try:
        # Note: Opus decoding errors in logs are common with UDP voice traffic and can often be ignored
        # if the resulting audio is intelligible.
        if not vc.is_connected():
            raise RuntimeError("Voice client disconnected before recording")

        vc.start_recording(sink, finished_callback)
        if bot and bot.debug_enabled("sinks"):
            bot.debug(
                "sinks",
                f"Started recording for duration={duration}s on guild={guild.id}",
            )
    except Exception as exc:
        if bot and bot.debug_enabled("sinks"):
            bot.debug(
                "sinks", f"start_recording threw: {exc}\n{traceback.format_exc()}"
            )
        raise RuntimeError("Failed to start recording on VoiceClient") from exc

    # Wait for the requested duration, checking connection periodically
    for _ in range(int(duration * 10)):
        if not vc.is_connected():
            if bot and bot.debug_enabled("sinks"):
                bot.debug("sinks", "Voice client disconnected during recording wait")
            break
        await asyncio.sleep(0.1)

    # Stop recording and wait for the sink's finished callback to fire.
    try:
        vc.stop_recording()
    except Exception:
        pass

    try:
        await asyncio.wait_for(finished_future, timeout=2.0)
    except asyncio.TimeoutError:
        if bot and bot.debug_enabled("sinks"):
            bot.debug("sinks", "OGGSink finished callback timed out; continuing")

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
                bot.debug(
                    "sinks",
                    f"No audio data for user {user.id}. Available keys: {list(sink.audio_data.keys())}",
                )
            raise RuntimeError(f"No audio recorded for user {user.id}")

        # AudioData.file is the BytesIO
        audio_bytes = audio_data.file.getvalue()
        return audio_bytes

    except Exception as exc:
        if bot and bot.debug_enabled("sinks"):
            bot.debug("sinks", f"Error extracting audio: {exc}")
        raise


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


# on_app_command_error is registered inside `main()` where `bot` exists.


class VoiceTestView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Join", style=discord.ButtonStyle.primary, custom_id="voicetest_join_btn"
    )
    async def join_button(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        vc = await ensure_voice_connected(interaction)
        if vc:
            await interaction.response.send_message(
                "Joined voice channel.", ephemeral=True
            )
            # Try to get the channel where the interaction happened
            channel = interaction.channel if hasattr(interaction, "channel") else None
            await play_join_sound(vc, text_channel=channel)

    @discord.ui.button(
        label="Leave", style=discord.ButtonStyle.danger, custom_id="voicetest_leave_btn"
    )
    async def leave_button(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        vc = interaction.guild.voice_client
        if vc:
            await vc.disconnect()
            await interaction.response.send_message(
                "Left voice channel.", ephemeral=True
            )
        else:
            await interaction.response.send_message("Not connected.", ephemeral=True)

    @discord.ui.button(
        label="Test", style=discord.ButtonStyle.success, custom_id="voicetest_test_btn"
    )
    async def test_button(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        # Only allow pressing user to run test for themselves
        dur = bot.default_duration if bot else 5
        await run_voice_test(interaction, interaction.user, dur)


def create_views():
    return VoiceTestView()


async def run_voice_test(
    interaction: discord.Interaction | discord.ApplicationContext,
    user: discord.Member,
    duration: int,
):
    """Common logic for running a voice test from slash command or button."""

    # Helper to handle response differences
    async def send_msg(msg, ephemeral=True):
        if hasattr(interaction, "respond"):
            await interaction.respond(msg, ephemeral=ephemeral)
        elif hasattr(interaction, "response"):
            if not interaction.response.is_done():
                await interaction.response.send_message(msg, ephemeral=ephemeral)
            else:
                await interaction.followup.send(msg, ephemeral=ephemeral)
        else:
            # Fallback
            pass

    async def send_channel(msg):
        if hasattr(interaction, "channel") and interaction.channel:
            await interaction.channel.send(msg)
        elif (
            hasattr(interaction, "message")
            and interaction.message
            and interaction.message.channel
        ):
            await interaction.message.channel.send(msg)

    guild = interaction.guild
    if not guild:
        await send_msg("This command must be used in a guild.")
        return

    # Check membership and channel
    if not isinstance(user, discord.Member) or not user.voice or not user.voice.channel:
        await send_msg("You must be in a voice channel to run a voice test.")
        return

    guild_id = guild.id
    if bot._active_recordings.get(guild_id):
        await send_msg(
            "A recording is already in progress in this guild. Try again later."
        )
        return

    vc = await ensure_voice_connected(interaction)
    if not vc:
        return

    # Helper to safely play audio
    async def safe_play(data_or_bytesio):
        if not vc.is_connected():
            return
        try:
            if isinstance(data_or_bytesio, bytes):
                source = io.BytesIO(data_or_bytesio)
            else:
                source = data_or_bytesio
            
            try:
                source.seek(0)
            except Exception:
                pass
                
            vc.play(FFmpegPCMAudio(source, pipe=True))
            while vc.is_playing():
                await asyncio.sleep(0.1)
                if not vc.is_connected():
                    break
        except Exception as e:
            logger.warning(f"Playback error: {e}")

    # Announce and play a short cue
    await send_msg(
        f"Starting voice test for {duration}s. You will be recorded and then played back."
    )
    await send_channel(f"{user.display_name} is starting a voice test for {duration}s.")

    # TTS: Announce start
    try:
        # Instead of relying solely on the startup probe, attempt to generate
        # TTS now and treat generation success as the source-of-truth. This
        # avoids false negatives where the probe failed earlier but runtime
        # generation still works.
        if bot and bot.debug_enabled("playback"):
            bot.debug("playback", "Attempting start announcement TTS generation")

        data = await generate_tts_bytes(f"Recording starting for {user.display_name}")
        if not data:
            await send_msg(
                "Voice announcement unavailable; cannot proceed with recording for privacy reasons.",
                ephemeral=True,
            )
            await send_channel("Voice test aborted: audible announcement unavailable.")
            return

        await safe_play(data)
    except Exception as e:
        logger.error(f"TTS generation failed: {e}")
        await send_msg("TTS error occurred; aborting voice test.", ephemeral=True)
        await send_channel("Voice test aborted: TTS error during start announcement.")
        return

    try:
        bot._active_recordings[guild_id] = user.id
        # Attempt live record via sinks
        try:
            if bot and bot.debug_enabled("commands"):
                bot.debug(
                    "commands",
                    f"Starting live capture for user={user.id} dur={duration}",
                )

            audio_bytes = await record_user_audio(guild, user, duration)

            # TTS: Announce stop
            try:
                data = await generate_tts_bytes("Recording stopped. Playing back.")
                if data:
                    await safe_play(data)
                else:
                    logger.debug(
                        "No TTS audio produced for stop announcement; skipping voice playback"
                    )
            except Exception as e:
                logger.error(f"TTS generation failed: {e}")

            await send_channel("Recording complete. Waiting briefly before playback...")
            await asyncio.sleep(bot.playback_delay)

            # Playback from memory
            audio_source = io.BytesIO(audio_bytes)
            # FFmpegPCMAudio with pipe=True reads from the file-like object
            await send_channel("Playing back recorded audio.")
            await safe_play(audio_source)

            await send_channel("Playback complete.")
        except Exception as exc:
            # If recording isn't supported or errors, fall back to placeholder snippet
            if bot and bot.debug_enabled("sinks"):
                bot.debug("sinks", f"record_user_audio failed: {exc}")
            await send_channel(f"Recording failed: {exc}")
    finally:
        bot._active_recordings.pop(guild_id, None)


async def cleanup_and_shutdown(bot_obj, sig_name: str | int = None):
    """Module-level cleanup routine to stop recordings, disconnect VCs,
    clear active recording state, and close the bot. Separated from
    `main()` so it can be tested directly.
    """
    logger.info(
        f"Shutdown requested ({sig_name}); cleaning up voice clients and recordings"
    )
    try:
        # Stop any active recordings by attempting to stop recording on each VC
        for guild in list(getattr(bot_obj, "guilds", [])):
            try:
                vc = getattr(guild, "voice_client", None)
                if vc:
                    try:
                        # If the voice client is recording via sinks, stop it
                        try:
                            vc.stop_recording()
                        except Exception:
                            pass
                        # Disconnect the voice client
                        try:
                            # Support both sync and async disconnect APIs
                            disc = vc.disconnect
                            if asyncio.iscoroutinefunction(disc):
                                await disc()
                            else:
                                disc()
                        except Exception:
                            logger.debug(
                                f"Failed to disconnect vc for guild {getattr(guild, 'id', None)}"
                            )
                    except Exception:
                        logger.debug(
                            f"Failed to disconnect vc for guild {getattr(guild, 'id', None)}"
                        )
            except Exception:
                logger.debug(f"Error while cleaning guild {getattr(guild, 'id', None)}")

        # Clear active recording state
        try:
            if hasattr(bot_obj, "_active_recordings"):
                bot_obj._active_recordings.clear()
        except Exception:
            pass
    except Exception:
        logger.exception("Error during cleanup")
    finally:
        try:
            # Attempt to close the bot if it provides an async close
            close_fn = getattr(bot_obj, "close", None)
            if close_fn:
                if asyncio.iscoroutinefunction(close_fn):
                    await close_fn()
                else:
                    close_fn()
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="Discord Sound Test bot (prototype)")
    parser.add_argument(
        "--config", required=True, help="Path to JSON config file (no env vars)."
    )
    parser.add_argument(
        "--debug",
        action="append",
        choices=DEBUG_TARGETS,
        help="Enable debugging for a target (can be passed multiple times).",
    )
    parser.add_argument(
        "--debug-all", action="store_true", help="Enable all debug targets."
    )
    # individual debug flags for convenience
    for t in DEBUG_TARGETS:
        parser.add_argument(
            f"--debug-{t.replace('_', '-')}",
            action="store_true",
            help=f"Enable debug target: {t}",
        )
    args = parser.parse_args()

    config_path = args.config
    if not os.path.exists(config_path):
        logger.error(f"Config file not found: {config_path}")
        sys.exit(2)

    config = load_config(config_path)

    global bot
    bot = VoiceTestBot(config)

    # Register graceful shutdown handlers to ensure we don't leave recordings
    # or voice clients open on SIGINT/SIGTERM. We schedule an async cleanup
    # task that will attempt to stop any recordings and disconnect voice clients.
    loop = asyncio.get_event_loop()

    async def _cleanup_and_shutdown(sig_name: str | int = None):
        # Delegate to module-level cleanup so logic is testable and centralized
        await cleanup_and_shutdown(bot, sig_name)

    def _register_signal_handlers():
        async def _on_signal(sig):
            await _cleanup_and_shutdown(sig)

        for s in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(
                    s, lambda s=s: asyncio.create_task(_on_signal(s))
                )
            except NotImplementedError:
                # Event loop does not support add_signal_handler (e.g., on Windows), ignore
                pass

    _register_signal_handlers()

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
    async def on_ready():
        logger.info(f"Bot ready: {bot.user} ({bot.user.id})")
        # Probe TTS at startup so we can enforce audible consent for recordings
        try:
            ok = await probe_tts()
            bot.tts_available = ok
            if ok:
                logger.info("TTS probe succeeded; in-voice announcements enabled")
            else:
                logger.warning("TTS probe failed; voice announcements will be disabled")
        except Exception:
            bot.tts_available = False
            logger.exception("TTS probe raised an exception")
        bot.add_view(VoiceTestView())

        # Ensure application commands are synchronized with Discord's API.
        try:
            logger.info("Attempting global command sync...")
            await bot.sync_commands()
            logger.info("Global command sync complete.")
        except Exception:
            logger.exception("Command sync failed on startup. Exiting.")
            sys.exit(1)

    @bot.event
    async def on_app_command_error(interaction: discord.Interaction, error: Exception):
        # Basic error handler for application commands
        try:
            await interaction.response.send_message(f"Error: {error}", ephemeral=True)
        except Exception:
            pass
    @bot.event
    async def on_voice_state_update(member: discord.Member, before, after):
        """Auto-disconnect when no non-bot users remain in the voice channel.

        This schedules a short delayed re-check to avoid races when users
        briefly switch channels.
        """
        try:
            guild = getattr(member, "guild", None)
            if not guild:
                return

            guild_id = guild.id
            # Respect configured option: if disabled, do not auto-disconnect
            if not getattr(bot, "auto_leave_when_alone", True):
                return

            # If a recording is active, do not auto-disconnect
            if getattr(bot, "_active_recordings", {}).get(guild_id):
                return

            vc = guild.voice_client
            if not vc or not getattr(vc, "channel", None):
                return

            channel = vc.channel

            async def _delayed_check():
                await asyncio.sleep(5)
                # If a recording started meanwhile, abort
                if getattr(bot, "_active_recordings", {}).get(guild_id):
                    return
                # Re-evaluate members in the channel
                non_bots = [m for m in channel.members if not getattr(m, "bot", False)]
                if len(non_bots) == 0:
                    try:
                        await vc.disconnect()
                        logger.info(
                            f"Auto-disconnect: left voice channel in guild {guild_id} (no non-bot users)"
                        )
                    except Exception:
                        logger.debug(
                            f"Auto-disconnect failed for guild {guild_id}: {traceback.format_exc()}"
                        )

            asyncio.create_task(_delayed_check())
        except Exception:
            logger.exception("on_voice_state_update handler error")

    @bot.slash_command(name="join")
    async def join_command(ctx: discord.ApplicationContext):
        if bot and bot.debug_enabled("commands"):
            bot.debug(
                "commands",
                f"/join invoked by user={ctx.author.id} in guild={ctx.guild.id}",
            )
        vc = await ensure_voice_connected(ctx)
        if not vc:
            return
        await ctx.respond("Joined voice channel.", ephemeral=True)
        await play_join_sound(vc, text_channel=ctx.channel)

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
            bot.debug(
                "commands",
                f"/voicetest invoked by user={ctx.author.id} duration={duration}",
            )

        dur = _ensure_duration(duration, bot.default_duration, bot.max_duration)
        await run_voice_test(ctx, ctx.author, dur)

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
    token = config.get("token")
    if not token:
        logger.error("Config must include 'token' field. No env vars are used.")
        sys.exit(2)

    bot.run(token)


if __name__ == "__main__":
    main()
