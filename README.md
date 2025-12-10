# Discord Sound Test Bot

A privacy-first Discord bot designed for users to test their microphone quality and settings. The bot records a short clip of audio from the user and immediately plays it back, allowing them to verify how they sound to others.

## Key Features

*   **Privacy-First**: Records only when explicitly triggered via slash commands.
*   **Ephemeral Storage**: Audio is stored strictly in-memory and is discarded immediately after playback. No audio is ever written to disk or uploaded to external servers.
*   **Audible Consent**: Uses local TTS (`espeak-ng`) to announce the start and end of recordings. If TTS is unavailable, recording is disabled to ensure users are always aware when they are being recorded.
*   **Stack**: Built with Python 3.12 and `py-cord`, utilizing native OGG/Opus sinks for high-quality audio capture.

---

## Discord Bot Setup Guide

Before installing the bot locally, you need to create the application in Discord and generate an invite link.

1.  **Create Application**: Go to the [Discord Developer Portal](https://discord.com/developers/applications) and create a new application.
2.  **Add Bot User**: Navigate to the **Bot** tab and click "Add Bot".
3.  **Privileged Intents**: In the Bot settings, you **must** enable the following Privileged Gateway Intents:
    *   **Server Members Intent**
    *   **Message Content Intent** (optional, but recommended)
4.  **Copy Token**: Click "Reset Token" to generate your bot token. You will need this for `config.json`.

### Generating an Invite Link

To invite the bot to your server, use the OAuth2 URL generator (under the **OAuth2** > **URL Generator** tab) or construct the URL manually.

**Scopes:**
*   `bot`
*   `applications.commands`

**Bot Permissions:**
*   `Connect`
*   `Speak`
*   `View Channels`
*   `Send Messages` (optional, for text feedback)

**Manual Invite Link Example:**
Replace `CLIENT_ID_HERE` with your Application ID.

```
https://discord.com/oauth2/authorize?permissions=3214336&scope=bot%20applications.commands&client_id=CLIENT_ID_HERE
```

*Note: The permission integer `3214336` includes Connect, Speak, and View Channels. You can calculate your own integer using the Developer Portal.*

---

## Discord-sound-test Prerequisites & System Dependencies

To run this bot, you need the following system dependencies installed. These are required for audio processing and Text-to-Speech generation.

*   **Python 3.12+**
*   **FFmpeg**: Required for audio playback.
*   **eSpeak NG**: Required for generating TTS announcements.

### Installing System Dependencies

**Debian/Ubuntu:**
```bash
sudo apt-get update
sudo apt-get install -y ffmpeg espeak-ng libsndfile1
```

**macOS (Homebrew):**
```bash
brew install ffmpeg espeak-ng
```

---



## Installation & Setup

### 1. Clone and Configure

1.  Clone the repository.
2.  Copy the example configuration file:
    ```bash
    cp config.example.json config.json
    ```
3.  Edit `config.json` and add your Discord Bot Token.
    *   *Note: This project intentionally uses a JSON config file instead of environment variables for configuration.*

### 2. Python Environment

It is recommended to use a virtual environment.

```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install production dependencies
pip install -r requirements.txt

# (Optional) Install development/testing tools
pip install -r requirements-dev.txt
```

*   `requirements.txt`: Core dependencies for running the bot (`py-cord`, `PyNaCl`, etc.).
*   `requirements-dev.txt`: Tools for testing and linting (`pytest`, `black`, `ruff`).

Note: The older UI that posted message buttons via `/postvoicetestcommands` has been removed; the bot exposes only slash commands now: `/join`, `/leave`, `/voicetest`, and `/stop`.

---

## Running the Bot

### Local Execution

Once configured and dependencies are installed:

```bash
python3 bot.py --config config.json
```

### Docker Deployment

The project includes a production-ready `Dockerfile` and `docker-compose.yml`.

**Using Docker Compose:**

1.  Ensure `config.json` is configured.
2.  Run the container:
    ```bash
    docker-compose up -d --build
    ```

**Manual Docker Run:**

```bash
# Build the image
docker build -t discord-sound-test .

# Run with config mounted
docker run -d \
  --name voice-test \
  -v $(pwd)/config.json:/app/config.json:ro \
  discord-sound-test --config /app/config.json
```

---

## Development & Testing

The project includes a suite of tests to verify functionality, particularly the TTS and cleanup logic.

### Running Tests

Ensure you have installed the dev dependencies (`requirements-dev.txt`).

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=bot
```

### Project Structure

*   `bot.py`: The main entry point and bot logic. Contains the `VoiceTestBot` class and slash command definitions.
*   `Dockerfile`: Multi-stage build for creating a lightweight production image.
*   `tests/`: Contains `pytest` test suites.
    *   `test_tts.py`: Verifies TTS generation and fallbacks.
    *   `test_cleanup.py`: Ensures resources are freed on shutdown.
*   `config.json`: Runtime configuration (ignored by git).

---

## License & Privacy

*   **License**: See `LICENSE` for usage terms.
*   **Privacy Policy**: See `PRIVACY.md` for details on data handling.
*   **Terms of Service**: See `TERMS.md`.

