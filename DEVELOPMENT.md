# Local Development Setup for Resonance

## Quick Start

```bash
# 1. Clone and set up environment
git clone https://github.com/whorne89/Resonance.git
cd Resonance

# 2. Sync Python dependencies (uv manages venv automatically)
uv sync

# 3. Run the app
python -m src.main
```

## Optional: Pre-download Post-Processor

If you plan to test Post-Processing or want to avoid first-run delays:

```bash
python scripts/setup_postprocessor.py
```

This downloads:

- llama-server binary (~2-20 MB depending on platform)
- Qwen 2.5 GGUF model (~1.1 GB)

**One-time setup.** Cached for all future launches.

## Features & First Use

### No Setup Needed

- Basic dictation (Whisper)
- Hotkeys
- Custom dictionary
- Usage statistics

### Optional (Auto-downloaded on first use)

- Post-Processing: Settings > Toggle ON > Downloads ~1.1 GB (first time only)
- On-Screen Recognition (OCR): Requires OCR engine (see next section)
- Self-Learning: Requires Post-Processing + OCR

## OCR Setup (Optional)

For On-Screen Recognition (OSR) on local dev:

**Windows:** No setup needed — uses built-in Windows OCR (winocr).

**Linux:**

```bash
sudo apt-get install tesseract-ocr
```

**macOS:**

```bash
brew install tesseract
```

## Development Workflow

1. **Edit code** > Changes take effect on restart
2. **Test features**:

   ```bash
   python -m src.main
   # Right-click tray icon > Settings to configure
   ```

3. **Check logs**:

   ```bash
   # Windows
   cat .resonance/logs/resonance.log

   # Linux/macOS
   cat ~/.resonance/logs/resonance.log
   ```

4. **Rebuild EXE for testing** (Windows):
   ```bash
   uv pip install pyinstaller
   pyinstaller resonance.spec -y
   ./dist/Resonance/Resonance.exe
   ```

## Platform Notes

### Windows
- OCR uses native Windows OCR (winocr) — no setup needed
- Sound effects use Qt multimedia (QSoundEffect)
- Hotkeys work out of the box via pynput

### Linux
- OCR uses Tesseract — install via `apt-get install tesseract-ocr`
- Sound effects require GStreamer (`gstreamer1.0-plugins-good`)
- Some desktop environments may block global hotkeys (see Troubleshooting)

### macOS
- OCR uses Tesseract — install via `brew install tesseract`
- Hotkeys require Accessibility permissions in System Settings

## Troubleshooting

### Import errors

```bash
# Re-sync dependencies
uv sync --upgrade
```

### Post-Processing not working

```bash
# Manual download
python scripts/setup_postprocessor.py

# Check logs
tail -50 .resonance/logs/resonance.log
```

### Hotkeys not working on Linux

Some Linux desktop environments block global hotkeys. Try:

- **GNOME**: Settings > Keyboard > Custom shortcuts
- **KDE**: System Settings > Shortcuts > Custom Shortcuts
- **i3/awesome**: Configure in window manager config

### "Tesseract not found" (Linux/macOS)

Install via package manager (see OCR Setup above), or skip OCR for basic testing.

## Building for Distribution

```bash
# Pre-download optional components
python scripts/setup_postprocessor.py

# For Tesseract bundling (Windows EXE only)
# Place tesseract/ directory in project root (see docs/tesseract-bundling.md)

# Build
uv pip install --upgrade pyinstaller
pyinstaller resonance.spec -y

# Output: dist/Resonance/Resonance.exe
```

See [docs/post-processor-installation.md](docs/post-processor-installation.md) for detailed setup options.
