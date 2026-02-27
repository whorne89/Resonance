# Resonance - Claude Code Memory

## Project Overview
Resonance is a Windows voice-to-text desktop application that uses Whisper (via faster-whisper) for speech recognition. It runs as a system tray application — hold a hotkey to record, release to transcribe, and the text is typed into whatever window is focused.

## Tech Stack
- **Python 3.12** — pinned via `.python-version`; uv manages the venv
- **GUI**: PySide6 (Qt for Python)
- **Audio**: sounddevice
- **Transcription**: faster-whisper (CTranslate2 backend, CPU only)
- **Hotkeys**: pynput
- **Typing output**: pynput keyboard + pyperclip
- **Threading**: QThread for async transcription
- **Config**: JSON-based settings

## Architecture
```
src/
  main.py                    - App entry point, VTTApplication controller, transcription worker
  core/
    audio_recorder.py        - Audio capture using sounddevice
    transcriber.py           - Whisper model loading and transcription
    keyboard_typer.py        - Keyboard input simulation (type or paste)
    hotkey_manager.py        - Global hotkey registration (pynput)
  gui/
    system_tray.py           - System tray icon with context menu
    settings_dialog.py       - Settings UI (hotkey, model, audio, typing, dictionary)
    dictionary_dialog.py     - Custom dictionary editor UI
  utils/
    config.py                - ConfigManager (JSON settings)
    resource_path.py         - Path resolution (app data, resources)
    logger.py                - Logging with file rotation
  resources/
    icons/                   - Tray icons (idle, recording)
```

## Key Design Decisions
- **App data stored relative to application directory** (not user home). Data lives in `<app_root>/.resonance/` so models, logs, and config stay on the same drive as the app.
- **Custom dictionary** for post-transcription word replacement. Stored in config under `dictionary.replacements`. Case-insensitive matching, applied in `VTTApplication.apply_dictionary()`.
- **No PyInstaller bundling currently** — the app runs directly as a Python script. Plan to package with PyInstaller when features stabilize.
- **CPU only** — GPU support deferred. See GPU section below.

## Versioning
- **Single source of truth**: `version` field in `pyproject.toml` (currently 1.2.0)
- About dialog reads via `importlib.metadata.version('resonance')` — never hardcode version strings
- Package must be installed in editable mode (`uv pip install -e .`) for importlib.metadata to work

## Transcription Flow
1. User holds hotkey -> AudioRecorder captures audio
2. User releases hotkey -> Audio sent to TranscriptionWorker (QThread)
3. Worker calls Transcriber.transcribe() -> returns text
4. VTTApplication.on_transcription_complete() applies dictionary replacements
5. KeyboardTyper.type_text() outputs to active window

## Whisper Models
- Dropdown uses display-name → model-ID mapping with `QComboBox.addItem(name, userData=id)`
- distil-whisper models use full HF repo IDs: `Systran/faster-distil-whisper-large-v3`
- HF cache dir converts `/` → `--`: `models--Systran--faster-distil-whisper-large-v3`
- `transcriber.is_model_downloaded()` handles both short names (`small`) and full repo IDs

## GPU Status — CPU Only For Now
- **CUDA is ruled out** — CTranslate2 needs exact CUDA version match (cublas64_12.dll), doesn't bundle runtime, NVIDIA-only. Not viable for distribution.
- **Future GPU path**: switch transcription engine to **whisper.cpp** (via pywhispercpp) with **Vulkan** backend. Vulkan runtime ships with all modern GPU drivers (NVIDIA, AMD, Intel). No user install needed.
- **CPU performance is adequate**: 5s audio transcribes in ~2.2s on Ryzen 3700X with `small` model (0.44x real-time factor). GPU would be ~0.3s.
- **Decision**: ship CPU-only, add GPU as a v2 feature after the app is packaged and stable.

## Config Location
Settings stored at `<app_root>/.resonance/settings.json`

## Common Gotchas
- `get_app_data_path()` in resource_path.py determines where all persistent data goes (models, config, logs)
- Logger must import from resource_path to stay consistent with the data path
- TranscriptionWorker runs in QThread — signals connect back to main thread
- Settings dialog creates a fresh instance each time it's opened (not reused)
- `QTimer.singleShot` from `threading.Thread` silently fails — use `QObject` signals for cross-thread UI updates
- `ctypes.CDLL("name.dll")` is unreliable on Windows even with PATH set — use full path or `os.add_dll_directory()`
- `uv pip install` may target system Python; use `--python .venv/Scripts/python.exe` to be safe

## Abandoned Work
- **`feat/post-processing` branch** — grammar correction via llama-cpp-python; parked due to distribution complexity (no pre-built Python 3.12 wheels, CUDA build issues). Code preserved on branch.
