#!/bin/bash
# Resonance - Voice to Text (with console output)
# Launch script for Linux and macOS — keeps terminal open for debugging

echo ""
echo "================================================"
echo "         RESONANCE - Voice to Text"
echo "================================================"
echo ""
echo "Starting application..."
echo ""
echo "HOTKEY: Ctrl+Alt+R (hold while speaking)"
echo ""
echo "The tray icon will appear in your system tray."
echo ""
echo "RIGHT-CLICK icon to change hotkey in Settings"
echo ""
echo "First transcription: ~5-10 seconds (loading)"
echo "After that: 1-2 seconds per transcription"
echo ""
echo "================================================"
echo ""

cd "$(dirname "$0")"

# Use local cache to avoid filesystem issues
export UV_CACHE_DIR="$(pwd)/.uv-cache"

# Install uv if not present
if ! command -v uv &> /dev/null; then
    echo "Installing uv package manager..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

uv sync
uv run python -m src.main

echo ""
echo "================================================"
echo "Application stopped."
echo "================================================"
