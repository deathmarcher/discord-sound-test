
## Builder stage: install Python deps into a venv so this layer can be cached
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Build-time system packages needed to compile wheels
RUN apt-get update \
	&& apt-get install -y --no-install-recommends \
	   build-essential \
	   libsodium-dev \
	   libffi-dev \
	   libsndfile1 \
	&& rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and create a venv to cache installed packages
COPY requirements.txt /app/requirements.txt
COPY requirements-dev.txt /app/requirements-dev.txt
RUN python -m venv /opt/venv \
	&& /opt/venv/bin/pip install --upgrade pip \
	&& /opt/venv/bin/pip install --no-cache-dir -r /app/requirements-dev.txt


## Final stage: smaller runtime image that reuses the venv from builder
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Runtime system packages (ffmpeg + espeak-ng and runtime libs)
RUN apt-get update \
	&& apt-get install -y --no-install-recommends \
	   ffmpeg \
	   espeak-ng \
	   libsndfile1 \
	   libsodium-dev \
	   libffi-dev \
	&& rm -rf /var/lib/apt/lists/*

# Copy the prebuilt virtualenv from the builder stage
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Copy only the application files we want in the image. Do NOT copy
# user-provided runtime config files (e.g., config.json) or other local
# artifacts. The operator should mount a config file at runtime.
COPY bot.py /app/bot.py
COPY discord_sound_test /app/discord_sound_test
COPY tests /app/tests
COPY README.md /app/README.md
COPY DESIGN.md /app/DESIGN.md

# Default entrypoint runs the top-level `bot.py`. At runtime the operator
# must provide `--config /path/to/config.json` (typically by mounting it).
ENTRYPOINT ["python", "bot.py"]


