# Discord Sound Test

Privacy-first Discord voice test prototype that performs short, single-user voice tests.

Quick start (after editing `config.json`):

1. Create and activate a virtualenv in the project root and install Python deps:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# (Optional) Install development and test dependencies:
pip install -r requirements-dev.txt
```

2. Copy `config.example.json` to `config.json` and fill in your bot `token`.

3. Run the bot directly:

```bash
python3 bot.py --config config.json
```

Discord bot setup and permissions
 - Create a Discord application at https://discord.com/developers and add a Bot user.
 - In the Bot settings, enable the "SERVER MEMBERS INTENT" if your chosen voice receive implementation requires it (library-dependent).
 - Copy the bot token into your `config.json` under the `token` field (this project does not use environment variables).
 - Recommended permissions the bot needs in servers where it will operate:
	 - Connect to voice channels (`CONNECT`)
	 - Speak in voice channels (`SPEAK`)
	 - View channels and read messages (`VIEW_CHANNEL`, `READ_MESSAGE_HISTORY` / `SEND_MESSAGES` as needed)
	 - Create slash commands (use the `applications.commands` scope)

Invite link example (replace `CLIENT_ID_HERE` and compute the permissions integer):

```
https://discord.com/oauth2/authorize?permissions=3214336&scope=bot%20applications.commands&client_id=CLIENT_ID_HERE
```

Notes on permissions integer:
 - You can compute the correct `PERMISSIONS_INTEGER` for the exact set of permissions using Discord's permissions calculator (or online tools) — include the `CONNECT` and `SPEAK` bits plus any message/interaction permissions you want the bot to have. If you leave `permissions=` out, the invite flow will let you select permissions interactively.

Security reminder
 - The project intentionally stores the bot token in `config.json` (no env vars). Treat `config.json` as a secret file: do not commit it to source control, and restrict access to it.

Notes:
- This project intentionally does not use environment variables; the bot token must be supplied inside the JSON config file passed via `--config`.
- `bot.py` is the canonical implementation for the prototype's voice flows; it uses in-memory capture and playback and documents areas where production hardening or alternate receive implementations may be desired.

System dependencies
- `ffmpeg` (used for playback)
- `espeak-ng` (or `espeak`) — used for local, in-memory TTS generation

