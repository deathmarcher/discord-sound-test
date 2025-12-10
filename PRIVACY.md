# Privacy Policy — Discord Sound Test

Last updated: 2025-12-10

This Privacy Policy describes how the Discord Sound Test bot ("the Bot")
handles data when it is run by a server operator. The Bot is a developer
prototype intended for local, privacy-first voice testing and is designed to
minimize data collection and retention.

Scope and operator-specific notice
----------------------------------
These policies apply to the instance of the Bot operated by the original
developer under the Discord application ID `1448050116811292853`.
If you run your own copy of the Bot (for example, by deploying from this
repository), you are responsible for your own operational practices and any
variations in behavior; the LICENSE in this repository does not change the
rights of others who fork or run their own instances.

If you are a server operator, you are responsible for configuring and
operating the Bot, and for informing your server members about its behavior.

1. What data the Bot may access
--------------------------------
- Discord account and membership metadata accessible via the Discord API for
  operation (usernames, user IDs, guild IDs, channel IDs). These are required
  so the Bot can identify users, create slash commands, and connect to voice
  channels.
- In-voice audio captured when a user explicitly triggers `/voicetest` or
  presses the **Test** button. The Bot captures only the audio of the user who
  initiated the test, scoped to the voice channel in which the test was run.
- Configuration data provided by the operator in the `config.json` file
  (including the bot token). Treat `config.json` as secret — do not commit it
  to source control.

2. What the Bot does NOT do
---------------------------
- The Bot does NOT upload voice recordings, TTS, or any other audio to any
  external servers by default. All TTS generation and audio handling is local
  to the host running the Bot.
- The Bot does NOT persist audio recordings to disk. Recordings are captured
  into memory buffers (`io.BytesIO`) and are deleted as soon as the playback
  completes.
- The Bot does NOT share audio with third parties, analytics providers, or
  cloud-based speech services.

3. TTS and announcements
------------------------
- Audible announcements (join/start/stop messages) are produced using the
  locally installed `espeak-ng` utility (or similar local engine). If local
  TTS is not available or fails, the Bot will refuse to start a recording to
  preserve audible consent.

4. Retention and deletion
-------------------------
- Voice recordings are retained in-memory only for the duration necessary to
  perform playback to the initiating user. After playback completes, the
  in-memory buffer is discarded.
- The Bot does not maintain logs of audio content. Standard operational logs
  (textual logs) may be written to stdout or a log file by the server
  operator; these logs should not contain audio content.

5. Configuration and secrets
----------------------------
- The Bot uses a JSON config file (specified via `--config`) that contains
  operational settings and the Discord bot token. The project intentionally
  avoids using environment variables; treat the config file as secret.
- Do not commit `config.json` or tokens to public repositories.

6. Operator responsibilities
---------------------------
- Operators must ensure the host running the Bot is secure and that
  third-party access to the host is restricted.
- Operators should inform server members that voice tests will produce an
  audible announcement and that audio is recorded only when they explicitly
  trigger a test.

7. Changes to this policy
-------------------------
- The Bot is a prototype and may be updated. Operators who deploy updated
  versions should review release notes and the updated Privacy Policy in the
  repository. This file contains the authoritative policy tied to the
  repository version.

8. Contact
----------
- If you have questions about this project or this policy, open an issue on
  the project's GitHub repository or contact the repository owner.

By running the Bot, you acknowledge and accept the behaviors described in
this Privacy Policy. If you do not agree, do not run or invite the Bot to
your server.
