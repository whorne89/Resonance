#!/bin/bash
# Resonance - Voice to Text
# Launch script for Linux and macOS

cd "$(dirname "$0")"

# Use local cache to avoid filesystem issues
export UV_CACHE_DIR="$(pwd)/.uv-cache"

# Install uv if not present
if ! command -v uv &> /dev/null; then
    echo "Installing uv package manager..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# Only sync on first run (when .venv doesn't exist)
if [ ! -d ".venv" ]; then
    echo "First run — installing dependencies..."
    uv sync
fi

# Launch in background (no terminal window needed)
nohup uv run python -m src.main > /dev/null 2>&1 &
disown
