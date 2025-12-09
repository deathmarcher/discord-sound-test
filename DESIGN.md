

# Discord Sound Test — Design Document

## Overview

Purpose: build a privacy-focused Python Discord bot that joins voice channels, plays a configured join sound, and performs short, single-user voice tests that capture a specific user's audio for a short duration (default 5s) and immediately plays it back with a short delay before deleting it from memory. This document captures explicit constraints for implementation so Copilot can scaffold the project consistently.

Important constraints provided by the project owner:
- Never use environment variables. All configuration must come from a JSON config file passed via CLI.
- The main bot script must start with `#!/usr/bin/env python3` and accept a `--config` CLI argument pointing to the JSON config file.
- Prefer in-memory storage for recordings; only use temporary disk files if absolutely necessary and delete them immediately after use.

## Goals
- Single-user, user-triggered voice tests (only the requesting user can trigger their own test).
- Play a pre-recorded join sound (configurable path/URL) whenever the bot joins a voice channel.
- Record for a short configurable duration, play back the snippet after a configurable delay, then immediately delete any stored audio data.
- Avoid persistent storage of audio; ephemeral in-memory buffering only with immediate disposal.
- Provide a message-based UI (slash commands + an optional `/postvoicetestcommands` that posts a message with interactive buttons for join/leave/test).

## Non-goals
- No passive listening or background recording.
- No long-term storage, no uploading recordings to external services by default.

## Key Features (updated)
- `join` / `leave` voice actions.
- `voicetest` command (or button) that: announces the test, records only the invoking user's audio for N seconds (default 5), waits a short delay, plays it back into the same voice channel, then deletes it from memory.
- A `/postvoicetestcommands` command that posts a message with buttons for `Join`, `Leave`, and `Test` for easy use by server members.
- Rate-limiting and per-guild limits to avoid abuse.

## Commands & Interaction

- `--config /path/to/config.json` : CLI argument to specify the JSON config file (required). No env vars.
- Slash commands / interactions (preferred):
	- `/join` : Bot joins the caller's voice channel and plays configured join sound.
	- `/leave` : Bot leaves the channel.
	- `/voicetest duration:int = 5` : Trigger a voice test for the invoking user only. Flow:
		1. Bot replies (ephemeral) confirming the test and announces in voice channel that a test will start (audio or TTS) and the duration.
		2. Capture only the invoking user's audio for the specified duration.
		3. After capture, wait configurable `playback_delay` seconds.
		4. Play the captured snippet back into the same voice channel.
		5. Immediately discard the buffer from memory once playback completes (no metadata saved beyond a short-lived runtime reference for coordinating playback).
	- `/postvoicetestcommands` : Bot posts a message with buttons that let users make the bot `Join`, `Leave`, or start a `Test` (the `Test` button triggers the same flow and only allows the pressing user to record themselves).
	- `/stop` : Cancel ongoing recording or playback (if the user who started it issues `/stop`).

Policies on who can trigger tests:
- Only the user who initiates a test can trigger their own recording. Buttons and commands must enforce that the requester is the same as the target actor (interactions will check `interaction.user.id`).

UI notes:
- Use ephemeral confirmations where appropriate for privacy.
- Announce a visible and audible cue before recording begins in the voice channel (short sound or TTS) so all participants are aware.

## High-level Architecture (updated)

- Single Python process per deployment using a maintained `discord.py`-compatible library that supports voice receiving for capture.
- Voice manager per-guild that holds ephemeral runtime state: connected VoiceClient, current recording task, and a tiny in-memory buffer for the current test.
- Audio capture pipeline that filters by user ID and only buffers frames for that user.
- Playback pipeline that accepts in-memory PCM/Opus data (or a transient temp file if required by the library) and feeds it to the voice client via `FFmpegPCMAudio` or an Opus source, then deletes/discards the buffer immediately.

Important runtime constraints:
- Enforce one active recording per user at a time and one active recording per guild to keep complexity low.
- Global and per-guild rate limits configurable in the JSON config.

## Audio Capture & Format (privacy-first)

- Prefer capturing decoded PCM frames directly into an in-memory buffer (48 kHz, mono). The capture component must filter incoming frames by the invoking user's voice data only.
- Where the voice library requires files for playback, write to a securely created temporary file (in project `.tmp` or system tmp), feed `ffmpeg` or library for playback, then securely delete the file immediately (unlink and zeroing isn't necessary for this scope, but ensure deletion is immediate).
- We aim to have 2 methods. memory only or overflow into a .tmp file and we'll delete the .tmp file method later if we see that the in memory solution is possible without too much memory/performance issues
- Default file format for transient files: WAV for simplicity; playback can be performed through `ffmpeg` to ensure compatibility.
- Playback flow: record (in-memory) -> optional transient file -> playback -> delete buffer & file.

Configurable parameters in JSON:
- `join_sound`: path to an Opus/MP3/OGG file to play when joining.
- `default_duration`: default seconds to record (default 5).
- `max_duration`: absolute maximum (default 10).
- `playback_delay`: seconds to wait before playing back the recorded snippet (e.g., 1–2s).
- `rate_limits`: per-guild and per-user limits.
- `allowed_roles`: something to flesh out later that limits the usage down to certain discord roles. possibly per guild


## Storage & Lifecycle (strict privacy)

- NO persistent storage of audio or long-term metadata. The system must avoid writing any recordings to disk unless absolutely necessary for playback. If disk is used, files must be immediately deleted after playback.
- No list or delete commands for stored snippets since nothing is stored persistently. The `/list` and `/delete` commands are intentionally omitted in this privacy-first design (unless a very short-lived in-memory listing UI is desired, in which case it must be ephemeral and cleared after a short TTL).


## Join Sound Behavior

- The project will use a hard-coded join sound path inside the repository: `assets/join_sound.opus`.
- This sound is not supplied through the JSON config; instead the bot will reference the file at runtime directly. Expect the file to be added to the project (do not commit sensitive audio into public repos).
- On startup the bot will check that `assets/join_sound.opus` exists and is playable; if missing, the bot will fail to start with an error so you can add the asset.

## Concurrency, Rate-Limits & Safety

- Allow only one active `voicetest` per user at a time; reject overlapping requests.
- Apply per-guild rate-limits to avoid repeated abuse (configurable).
- Ensure permission checks: bot needs `CONNECT` and `SPEAK`. The bot should check and return actionable errors when missing.

## Permissions, Consent & Legal

- The bot must explicitly announce recording activity in the voice channel prior to capturing (audio cue + optional text announcement).
- Recordings occur only with explicit user action; no passive or background recording.

## Error handling & edge cases

- If the user is not in a voice channel, `/voicetest` fails with a helpful message.
- If voice receive is not supported by the chosen library or server settings block capture, the bot must inform the user and suggest alternative steps.
- If FFmpeg is missing or playback fails, return a clear error and clean up any transient buffers.

## Dependencies & Environment (explicit)

- Python 3.10+.
- Primary Python packages (to put in `requirements.txt`):
	- `discord.py>=2.0` (or a maintained fork that supports receive)
	- `PyNaCl`
	- `aiofiles` (optional)
	- `soundfile` or `numpy` (optional for audio processing)
- System: `ffmpeg` must be installed and available in `PATH`.

Important: do NOT use environment variables. Configuration must be passed via JSON config and CLI `--config`.

## Project structure & run conventions

Suggested repo items Copilot should scaffold:
- `bot.py` — main script, starts with `#!/usr/bin/env python3`, parses `--config` and uses the config JSON.
- `config.example.json` — example JSON config with fields: `token`, `join_sound`, `default_duration`, `max_duration`, `playback_delay`, `rate_limits` etc. (note: token will be kept in config file per your instructions — ensure security when sharing).
- `requirements.txt` — for pip install.
- `.venv/` — recommended virtual environment in project root (user requested).
- `scripts/run.sh` — wrapper that activates `.venv` and runs `bot.py` with `--config` (the script will be described in DESIGN but not created here).
- `assets/` — place for `join_sound` and other audio assets.

`scripts/run.sh` (design notes):
- Shell wrapper to: activate `.venv` (e.g., `source .venv/bin/activate`) and run `python bot.py --config config.json`.

Config file example (JSON schema snippet):
```json
{
	"token": "YOUR_DISCORD_TOKEN_IN_CONFIG_FILE",
	"join_sound": "assets/join_sound.opus",
	"default_duration": 5,
	"max_duration": 10,
	"playback_delay": 1,
	"rate_limits": { "per_guild": 5, "per_user": 2 }
}
```

Note: user explicitly requested no environment variables; the `token` will live in the JSON config and the bot must accept that via CLI.

## Testing

- Unit tests for the user-filtered recording pipeline (verify only the target user's frames are captured).
- Integration tests to verify join sound plays on join, `/voicetest` records only caller audio and plays it back after the delay, and that buffers are cleaned after playback.

## Implementation plan for Copilot scaffolding

1. Create `bot.py` with shebang, CLI parsing (`argparse`) for `--config`, and JSON config loader.
2. Set up virtualenv instructions and `scripts/run.sh` wrapper to activate `.venv` and run the bot with the config argument.
3. Implement `/join` and play `join_sound` from config on connect.
4. Implement per-guild `VoiceManager` that supports `voicetest` for the invoking user only:
	 - Announce/notify start, capture user frames into `BytesIO` for configured duration, wait `playback_delay`, feed to playback, then discard.
5. Add interaction message posting (`/postvoicetestcommands`) that posts a message with `Join`, `Leave`, and `Test` buttons; ensure button interactions honor `interaction.user.id` ownership for `Test`.
6. Add simple rate-limit enforcement and configuration-driven limits.
7. Create `requirements.txt` containing the dependency list.

## Risks & Notes (updated)

- Storing a token in a config file increases risk; document secure handling of the config file and avoid committing it to VCS.
- Voice receive APIs vary; choose a library/fork that supports receiving user audio frames (verify before scaffold).
- Ensure the project respects guild policies and local laws regarding recording audio.

---

This design is now tuned for privacy (no env vars, ephemeral in-memory audio), single-user-triggered voice tests, join-sound behavior, and an interaction-based UI with buttons. Copilot can now use this `DESIGN.md` to scaffold the project files (`bot.py`, `requirements.txt`, sample `config.json`, and `scripts/run.sh`) if you ask it to.


