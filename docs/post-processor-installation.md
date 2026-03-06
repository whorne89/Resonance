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
   - Right-click tray icon → Settings
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
- Verifies checksums (if available from GitHub)

**Result:** Post-Processing is ready to use immediately in the Settings dialog, no download wait.

## Binary Distribution (EXE)

### Recommended: Lazy Download (Small EXE)

**Default behavior:**

- EXE is ~50-100 MB (no post-processor bundled)
- When user enables Post-Processing, binary + model are downloaded
- Downloads are cached locally for future launches

**Advantages:**

- ✅ Fast download/install for end users
- ✅ Post-processor is optional (saves bandwidth for users who don't need it)
- ✅ Supports offline model updates (update app, redownload models separately)

**User Experience:**

1. User installs `Resonance-3.2.3.zip`
2. Launches app, uses basic dictation immediately (works offline)
3. Optionally enables Post-Processing in Settings
4. One-time ~1.1 GB download (20-30 minutes on typical connection)
5. Post-Processing enabled for all future sessions

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

# Result: dist/Resonance/ includes everything offline
```

**EXE size with bundled post-processor:**

- Without: ~100 MB
- With: ~1.2 GB (1.1 GB model + 10+ MB binary + libs)

**To enable bundling in PyInstaller spec** (optional):

In `resonance.spec`, add:

```python
# Optionally bundle pre-downloaded post-processor for offline distributions
postproc_datas = []
postproc_binaries = []
if os.path.isdir('.resonance/bin'):
    postproc_binaries.extend([
        (os.path.join('.resonance/bin', f), 'postproc/bin')
        for f in os.listdir('.resonance/bin') if os.path.isfile(os.path.join('.resonance/bin', f))
    ])
if os.path.isdir('.resonance/models/postproc-gguf'):
    postproc_datas.extend([
        (os.path.join('.resonance/models/postproc-gguf', f), 'postproc/models')
        for f in os.listdir('.resonance/models/postproc-gguf') if os.path.isfile(os.path.join('.resonance/models/postproc-gguf', f))
    ])

# Then add to Analysis:
a = Analysis(
    ...
    binaries=ssl_binaries + fw_binaries + ct_binaries + postproc_binaries,
    datas=[...] + postproc_datas,
)
```

Then in `post_processor.py`, add fallback for bundled model:

```python
def _get_bin_dir(self):
    # Try bundled location first, fall back to app data
    if hasattr(sys, '_MEIPASS'):  # Running from PyInstaller
        bundled = os.path.join(sys._MEIPASS, 'postproc', 'bin')
        if os.path.isdir(bundled):
            return bundled
    return get_app_data_path("bin")
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
  ...
```

## Release & Asset Information

**Current Release:** `b8216` (llama.cpp)

**Platform-Specific Assets:**

- **Windows (x64):** `llama-b8216-bin-win-cpu-x64.zip`
- **Linux (Ubuntu x64):** `llama-b8216-bin-ubuntu-x64.tar.gz`
- **macOS (ARM64):** `llama-b8216-bin-macos-arm64.tar.gz`
- **macOS (x64):** `llama-b8216-bin-macos-x64.tar.gz`

These are downloaded automatically by `post_processor.py` on first use via `platform.system()` and `platform.machine()` detection.

## Troubleshooting

### "llama-server binary not found"

**Cause:** Binary download failed or incomplete.

**Fix:**

```bash
# Manually re-download
python scripts/setup_postprocessor.py

# Or in Python:
from src.core.post_processor import PostProcessor
p = PostProcessor()
p.download_model()
```

### "GGUF model not found"

**Cause:** Model download failed or incomplete.

**Fix:** Same as above.

### Download is slow

**Cause:** Large model file (~1.1 GB) and bandwidth limitations.

**Solution:**

- Download happens only once and is cached
- Subsequent launches use cached model
- Consider pre-downloading on fast connection before sharing

### Post-Processor works in dev but not in EXE

**Cause:** Bundled paths are different from app data paths.

**Check:**

- Verify files in `.resonance/bin/` and `.resonance/models/postproc-gguf/`
- If bundled, verify `sys._MEIPASS` override in `_get_bin_dir()`
- Check app logs (`.resonance/logs/`) for error details

## Platform-Specific Notes

### Windows

- Binary: `llama-server.exe` + `.dll` dependencies
- Installation: Automatic via `download_model()`
- Permissions: Executes as current user (no admin needed)

### Linux

- Binary: `llama-server` (stripped, executable bit set)
- Dependencies: `.so` files (glibc-based, matching platform)
- Installation: Sets executable bit automatically
- Requirements: glibc 2.29+ (Ubuntu 18.04+, Debian 10+)

### macOS

- Binary: `llama-server` (ARM64 only for now)
- Dependencies: `.dylib` files
- Installation: Sets executable bit, handles code signing (if needed)
- Requirements: macOS 11.0+ (ARM64 native)

## Future: Optional Updates

Post-processor can be updated independently from Resonance:

```bash
# User removes old model and re-runs setup
rm -rf ~/.resonance/models/postproc-gguf/
python scripts/setup_postprocessor.py

# Or through GUI: Check for model updates in Settings
# (not yet implemented, but framework is ready)
```

## Summary

| Scenario                     | Setup                           | First Use                       | Size         |
| ---------------------------- | ------------------------------- | ------------------------------- | ------------ |
| **Local Dev**                | `uv sync`                       | Settings toggle (auto-download) | App only     |
| **Local Dev (pre-download)** | `setup_postprocessor.py`        | Settings toggle (cached)        | App + 1.1 GB |
| **EXE (lazy download)**      | `pyinstaller resonance.spec -y` | Settings toggle (auto-download) | ~100 MB      |
| **EXE (bundled offline)**    | Pre-download + bundled spec     | Settings toggle (cached)        | ~1.2 GB      |

**Recommended for most users:** Lazy download (automatic on first use). Pre-downloading or bundling is optional for developers and offline distributions.
