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

- llama-server binary (~2-20 MB)
- Qwen 2.5 GGUF model (~1.1 GB)

**One-time setup.** Cached for all future launches.

## Features & First Use

### No Setup Needed ✅

- ✅ Basic dictation (Whisper)
- ✅ Hotkeys
- ✅ Custom dictionary
- ✅ Usage statistics

### Optional (Auto-downloaded on first use)

- Post-Processing: Settings → Toggle ON → Downloads ~1.1 GB (first time only)
- On-Screen Recognition (OCR): Requires Tesseract (see next section)
- Self-Learning: Requires Post-Processing + OCR

## OCR Setup (Optional)

For On-Screen Recognition (OSR) on local dev:

**Linux:**

```bash
sudo apt-get install tesseract-ocr
```

**macOS:**

```bash
brew install tesseract
```

**Windows:**
Download from: https://github.com/UB-Mannheim/tesseract/wiki

## Development Workflow

1. **Edit code** → Changes reload automatically on restart
2. **Test features**:

   ```bash
   python -m src.main
   # Right-click tray icon → Settings to configure
   ```

3. **Check logs**:

   ```bash
   cat ~/.resonance/logs/resonance.log
   ```

4. **Rebuild EXE for testing**:
   ```bash
   uv pip install pyinstaller
   pyinstaller resonance.spec -y
   ./dist/Resonance/Resonance.exe
   ```

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
tail -50 ~/.resonance/logs/resonance.log
```

### Hotkeys not working on Linux

Some Linux desktop environments block global hotkeys. Try:

- **GNOME**: Settings → Keyboard → Custom shortcuts
- **KDE**: System Settings → Shortcuts → Custom Shortcuts
- **i3/awesome**: Configure in window manager config

### "Tesseract not found" (OSR)

Install via package manager (see OCR Setup above), or skip OCR for basic testing.

## Tips

- **Logs**: Check `~/.resonance/logs/resonance.log` for debugging
- **Config**: Settings saved to `~/.resonance/settings.json`
- **Models cached**: Whisper models in `~/.cache/huggingface/`
- **Console mode**: `START RESONANCE (with console).bat` on Windows shows errors

## Building for Distribution

```bash
# Pre-download optional components
python scripts/setup_postprocessor.py  # For bundled offline build (optional)

# For Tesseract bundling (Windows)
# Place tesseract/ directory in project root (see tesseract-README.md)

# Build
uv pip install --upgrade pyinstaller
pyinstaller resonance.spec -y

# Output
dist/Resonance/Resonance.exe  # Windows
# or dist/Resonance/resonance    # Linux/macOS (py2app when added)
```

See [post-processor-installation.md](post-processor-installation.md) for detailed setup options.

## Next Steps

- **Report bugs**: GitHub Issues with logs + steps to reproduce
- **Contribute**: Fork → branch → Pull Request
- **Documentation**: Update `.md` files as you go

Happy hacking! 🚀
