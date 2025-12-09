#!/usr/bin/env bash
set -euo pipefail

# Wrapper to activate project .venv and run bot.py with a JSON config file
VENV_DIR=".venv"
CONFIG_FILE="config.json"

if [ ! -f "$CONFIG_FILE" ]; then
  echo "Config file '$CONFIG_FILE' not found. Copy config.example.json to config.json and edit it."
  exit 1
fi

if [ ! -d "$VENV_DIR" ]; then
  echo "Virtualenv not found in $VENV_DIR. Create one with: python3 -m venv $VENV_DIR"
  exit 1
fi

source "$VENV_DIR/bin/activate"
python3 bot.py --config "$CONFIG_FILE"
