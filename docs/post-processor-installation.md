# Post-Processor Installation Guide

This document describes how to install and configure the post-processor (llama-server + Qwen GGUF model) for both local development and binary distribution.

## Overview

The post-processor consists of two components:

- **llama-server binary** (~2-20 MB depending on platform)
- **Qwen 2.5 1.5B Instruct GGUF model** (~1.1 GB)

Both are downloaded automatically on first use, but can be pre-downloaded for offline development or bundled into the binary distribution.

## Local Development Setup

### Option 1: Automatic Download on First Use (Recommended)

1. **Clone and install the project:**

   ```bash
   git clone https://github.com/whorne89/Resonance.git
   cd Resonance
   uv sync
   ```

2. **Launch the app:**

   ```bash
   python -m src.main
   ```

3. **Enable Post-Processing in Settings:**
   - Right-click tray icon > Settings
   - Toggle "Post-Processing (AI)" ON
   - Progress dialog shows download (one-time, ~1.1 GB)
   - Model is cached to `.resonance/models/postproc-gguf/`

### Option 2: Pre-Download Before Development

If you want to avoid first-run delays during testing:

```bash
# Download binary + model
python scripts/setup_postprocessor.py

# Or just the binary (skip model for now)
python scripts/setup_postprocessor.py --no-model

# Or just the model (skip binary)
python scripts/setup_postprocessor.py --no-binary
```

**What this does:**

- Downloads llama-server binary to `.resonance/bin/`
- Downloads Qwen GGUF model to `.resonance/models/postproc-gguf/`
- Shows download progress with file sizes

**Result:** Post-Processing is ready to use immediately in the Settings dialog, no download wait.

## Binary Distribution (EXE)

### Recommended: Lazy Download (Small EXE)

**Default behavior:**

- EXE is ~50-100 MB (no post-processor bundled)
- When user enables Post-Processing, binary + model are downloaded
- Downloads are cached locally for future launches

### Optional: Bundled Offline Distribution

For organizations or air-gapped environments, pre-download the post-processor:

```bash
# 1. Download post-processor binaries and model
python scripts/setup_postprocessor.py

# 2. Verify files exist
ls -lh .resonance/bin/
ls -lh .resonance/models/postproc-gguf/

# 3. Build PyInstaller bundle
uv pip install pyinstaller
pyinstaller resonance.spec -y
```

## File Structure

After setup, the directory structure looks like:

```
.resonance/
  bin/
    llama-server              (Linux/macOS, ~2-10 MB)
    llama-server.exe          (Windows, ~2-10 MB)
    *.dll                     (Windows dependencies)
    *.so                      (Linux dependencies)
    *.dylib                   (macOS dependencies)
  models/
    postproc-gguf/
      qwen2.5-1.5b-instruct-q4_k_m.gguf  (~1.1 GB)
```

## Release & Asset Information

**Current Release:** `b8175` (llama.cpp)

**Platform-Specific Assets:**

- **Windows (x64):** `llama-b8175-bin-win-cpu-x64.zip`
- **Linux (Ubuntu x64):** `llama-b8175-bin-ubuntu-x64.tar.gz`
- **macOS (ARM64):** `llama-b8175-bin-macos-arm64.tar.gz`
- **macOS (x64):** `llama-b8175-bin-macos-x64.tar.gz`

These are downloaded automatically by `post_processor.py` on first use via `sys.platform` and `platform.machine()` detection.

## Troubleshooting

### "llama-server binary not found"

Binary download failed or incomplete.

```bash
python scripts/setup_postprocessor.py
```

### Download is slow

The model file is ~1.1 GB. Download happens only once and is cached. Consider pre-downloading on a fast connection.

### Post-Processor works in dev but not in EXE

Check `.resonance/logs/` for error details. Verify files exist in `.resonance/bin/` and `.resonance/models/postproc-gguf/`.

## Platform-Specific Notes

### Windows

- Binary: `llama-server.exe` + `.dll` dependencies
- Permissions: Executes as current user (no admin needed)

### Linux

- Binary: `llama-server` (executable bit set automatically)
- Dependencies: `.so` files (glibc-based)
- `LD_LIBRARY_PATH` is set automatically to the bin directory
- Symlinks for `.so.0` files are created if missing

### macOS

- Binary: `llama-server` (ARM64 and x64 supported)
- Dependencies: `.dylib` files
- `DYLD_LIBRARY_PATH` is set automatically to the bin directory
