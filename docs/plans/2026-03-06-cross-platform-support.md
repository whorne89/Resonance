# Cross-Platform Support Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make Resonance run on Windows, Linux, and macOS from a single codebase without regressing Windows functionality.

**Architecture:** Platform-conditional dependencies via pyproject.toml markers. Windows keeps native backends (winocr, ctypes.windll). Linux/macOS get cross-platform alternatives (pytesseract, pywinctl). Shared code (Qt GUI, faster-whisper, post-processor, sound effects) works everywhere.

**Tech Stack:** PySide6 QtMultimedia (sound), pytesseract (Linux OCR), pywinctl (Linux window detection), platform-specific llama-server binaries.

---

### Task 1: Platform-conditional dependencies in pyproject.toml

**Files:** Modify `pyproject.toml`

- Keep `winocr` as Windows-only: `"winocr>=0.0.8; sys_platform == 'win32'"`
- Add Linux/macOS deps with markers:
  - `"pytesseract>=0.3.10; sys_platform != 'win32'"`
  - `"pywinctl>=0.0.50; sys_platform != 'win32'"`
  - `"Pillow>=10.0.0; sys_platform != 'win32'"`

### Task 2: Cross-platform sound effects (QSoundEffect)

**Files:** Modify `src/core/sound_effects.py`

- Replace `import winsound` with `from PySide6.QtMultimedia import QSoundEffect` + `from PySide6.QtCore import QUrl`
- Create `QSoundEffect` instances in `__init__` for start/stop tones
- Replace `winsound.PlaySound()` calls with `QSoundEffect.play()`

### Task 3: Cross-platform post-processor (llama-server)

**Files:** Modify `src/core/post_processor.py`

- Add `_get_platform_info()` to detect OS/arch and return correct binary name + archive URL
- Update `download_model()` to handle both zip (Windows) and tar.gz (Linux/macOS)
- Set executable bit on Unix after extraction
- Add `_build_runtime_env()` for LD_LIBRARY_PATH on Linux
- Add `.so` symlink creation for Linux shared libs
- Update `_start_llama_server()` with platform-conditional subprocess flags
- Improve `_wait_for_health()` to detect early server exit with stderr capture

### Task 4: Audio recorder sample rate fallback

**Files:** Modify `src/core/audio_recorder.py`

- Try cascade of sample rates (16kHz → 48kHz → 44.1kHz → 32kHz → 22.05kHz)
- Add `_resample()` using numpy interpolation when device rate differs from 16kHz
- Make `get_devices()` work without WASAPI on Linux (fallback already exists)

### Task 5: Platform-conditional OCR in screen_context.py

**Files:** Modify `src/core/screen_context.py`

- Keep winocr path for Windows (unchanged)
- Add Tesseract path for Linux/macOS
- Platform-conditional `_get_foreground_window()`: ctypes on Windows, pywinctl on Linux
- Platform-conditional `_capture_window()`: RGBA for winocr, PIL Image for Tesseract
- Platform-conditional `_extract_text()`: winocr on Windows, pytesseract on Linux

### Task 6: Platform guard in main.py

**Files:** Modify `src/main.py`

- Wrap `import ctypes` and `set_windows_app_id()` in `sys.platform == 'win32'` check
