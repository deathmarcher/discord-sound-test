#!/usr/bin/env bash
# Rebuild and bring up the docker-compose services.
# This wrapper forces a fresh image build every time it's run.
set -euo pipefail
cd "$(dirname "$0")/.." || exit 1

# Use docker compose v2+ if available, fall back to docker-compose
DOCKER_COMPOSE_CMD=""
if command -v docker &>/dev/null && docker compose version &>/dev/null; then
  DOCKER_COMPOSE_CMD="docker compose"
elif command -v docker-compose &>/dev/null; then
  DOCKER_COMPOSE_CMD="docker-compose"
else
  echo "Error: docker compose or docker-compose not found" >&2
  exit 2
fi

echo "Building images (no cache)..."
$DOCKER_COMPOSE_CMD build --no-cache

echo "Starting services (detached)..."
$DOCKER_COMPOSE_CMD up -d --remove-orphans

echo "Done. To view logs: $DOCKER_COMPOSE_CMD logs -f"