# Resonance - Claude Code Memory

## Project Overview
Resonance is a Windows voice-to-text desktop application that uses Whisper (via faster-whisper) for speech recognition. It runs as a system tray application — hold a hotkey to record, release to transcribe, and the text is typed into whatever window is focused.

## Tech Stack
- **Python 3.12** — pinned via `.python-version`; uv manages the venv
- **GUI**: PySide6 (Qt for Python)
- **Audio**: sounddevice (recording), winsound (notification tones)
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
    audio_recorder.py        - Audio capture using sounddevice, exposes current_rms
    transcriber.py           - Whisper model loading and transcription
    keyboard_typer.py        - Keyboard input simulation (type or paste)
    hotkey_manager.py        - Global hotkey registration (pynput)
    dictionary.py            - Post-transcription word replacement (exact + fuzzy)
    post_processor.py        - LLM post-processing via llama-server (grammar/punctuation/filler cleanup)
    sound_effects.py         - Notification tones via winsound (WAV files)
  gui/
    system_tray.py           - System tray icon with context menu
    settings_dialog.py       - Settings UI (hotkey, model, audio, typing, dictionary)
    dictionary_dialog.py     - Custom dictionary editor UI
    recording_overlay.py     - Floating pill overlay with waveform visualization
  utils/
    config.py                - ConfigManager (JSON settings)
    resource_path.py         - Path resolution (app data, resources)
    logger.py                - Logging with file rotation
  resources/
    icons/                   - Tray icons (idle, recording)
```

## Key Design Decisions
- **App data stored relative to application directory** (not user home). Data lives in `<app_root>/.resonance/` so models, logs, and config stay on the same drive as the app.
- **Custom dictionary** for post-transcription word replacement. Stored in config under `dictionary.replacements`. Case-insensitive matching, applied via `DictionaryProcessor.apply()`.
- **Recording overlay** — frameless QPainter pill widget, always-on-top, click-through (`WindowTransparentForInput`). Shows pulsing red dot + live waveform bars during recording, animated blue dots during processing.
- **Sound effects** — generated as WAV files in `.resonance/sounds/`, played via `winsound.PlaySound(SND_FILENAME | SND_ASYNC)`. Users can drop custom `start.wav`/`stop.wav` to override defaults. Using winsound avoids conflicts with sounddevice recording.
- **Thread-safe hotkey handling** — hotkey callbacks emit Qt signals (`_hotkey_pressed`/`_hotkey_released`) to marshal execution from pynput background threads to the main Qt thread.
- **CPU only, GPU scrapped** — see GPU section below.

## Versioning
- **Single source of truth**: `version` field in `pyproject.toml` (currently 2.2.1)
- About dialog reads via `importlib.metadata.version('resonance')` — never hardcode version strings
- Package must be installed in editable mode (`uv pip install -e .`) for importlib.metadata to work

## Transcription Flow
1. User holds hotkey → start tone plays → AudioRecorder captures audio → overlay shows recording state
2. User releases hotkey → stop tone plays → audio sent to TranscriptionWorker (QThread) → overlay shows processing state
3. Worker calls Transcriber.transcribe() → PostProcessor.process() (if enabled) → returns text
4. VTTApplication.on_transcription_complete() applies dictionary replacements via DictionaryProcessor
5. KeyboardTyper.type_text() outputs to active window → overlay fades out

## Whisper Models
- Dropdown uses display-name → model-ID mapping with `QComboBox.addItem(name, userData=id)`
- distil-whisper models use full HF repo IDs: `Systran/faster-distil-whisper-large-v3`
- HF cache dir converts `/` → `--`: `models--Systran--faster-distil-whisper-large-v3`
- `transcriber.is_model_downloaded()` handles both short names (`small`) and full repo IDs
- **Model benchmarks (5s audio, Ryzen 3700X CPU)**:
  - tiny: sub-second, decent accuracy, inconsistent punctuation
  - base: sub-second, good accuracy
  - small: ~2s, good accuracy
  - distil-small.en: ~2s, good accuracy, English-optimized
  - distil-large-v3: too slow for dictation, removed from UI

## GPU — Scrapped
- **CUDA**: ruled out — CTranslate2 needs exact CUDA 12.x DLLs (cublas64_12.dll), user has CUDA 13.1. Not portable.
- **Vulkan via pywhispercpp**: tried and reverted — pywhispercpp CPU is ~2x slower than faster-whisper (4.5s vs 2.2s for 5s audio). Unacceptable latency for dictation.
- **Decision**: CPU-only with faster-whisper. GPU not needed — tiny model is already sub-second.

## Config Location
Settings stored at `<app_root>/.resonance/settings.json`
Custom sounds at `<app_root>/.resonance/sounds/start.wav` and `stop.wav`

## Common Gotchas
- `get_app_data_path()` in resource_path.py determines where all persistent data goes (models, config, logs, sounds)
- Logger must import from resource_path to stay consistent with the data path
- TranscriptionWorker runs in QThread — signals connect back to main thread
- Settings dialog creates a fresh instance each time it's opened (not reused)
- Hotkey callbacks fire from pynput background threads — must use Qt signals to marshal to main thread, never call GUI methods directly
- `winsound.PlaySound` cannot combine `SND_MEMORY` + `SND_ASYNC` on Windows — must write WAV files to disk and use `SND_FILENAME | SND_ASYNC`
- `uv pip install` may target system Python; use `--python .venv/Scripts/python.exe` to be safe

## Post-Processing
- **Backend**: llama-server (llama.cpp) with Qwen 2.5 1.5B Instruct GGUF (q4_k_m, ~1.1 GB)
- **Scope**: Grammar, capitalization, punctuation (periods, commas, question marks, quotation marks), contractions, sentence breaks, filler word removal (um, uh), and stutter/repeat cleanup
- **Prompt philosophy**: Conservative — keep every word the speaker said, only fix formatting. Do NOT summarize, shorten, or rephrase. Three explicit rules: (1) remove um/uh/stutters, (2) fix capitalization + punctuation, (3) fix grammar.
- **Hallucination guards**: Four-layer system in `_process_via_api()`: (1) filler-only input returns empty, (2) length guard rejects output >1.5x input, (3) answer-pattern guard, (4) question-answer guard
- **Lifecycle**: Tied to settings checkbox — created when ON, `.shutdown()` kills llama-server when OFF
- **Lazy loading**: Server subprocess starts on first `.process()` call, not at toggle-on
- **Pipeline**: Whisper → PostProcessor.process() → DictionaryProcessor.apply() → KeyboardTyper
- **Files**: llama-server.exe in `.resonance/bin/`, GGUF model in `.resonance/models/postproc-gguf/`

## UI Components (v2.1)
- **ToastNotification**: Dark pill at bottom-right, supports multi-line messages + bold details section. "Resonance" header at 15px bold.
- **ClipboardToast**: Small centered pill at bottom, shows "Text entered" (clipboard) or "Typing" (char-by-char)
- **RecordingOverlay**: Pill at bottom-center with waveform. Supports stacked feature badges above pill (e.g. "Post-Processing: ON") — only visible when features are enabled
- **AboutDialog**: RoundedDialog with 28px title, subtitle, description mentioning Whisper + Qwen, author, version from importlib.metadata
- **Startup toast**: Shows hotkey, model name, post-processing status, and entry method (details in bold)

## Future: macOS Support
- **Goal**: Single Python codebase that runs on both Windows and Mac
- **Platform-specific code is ~5%** — most of the app (Qt GUI, faster-whisper, sounddevice, config, post-processing) is already cross-platform
- **What needs abstraction**:
  - `winsound` → cross-platform alternative (e.g. `simpleaudio` or `playsound`) on Mac
  - `ctypes.windll` (app ID) → already in try/except, just skip on Mac
  - `pynput` hotkeys/typing → works on Mac but requires Accessibility permissions; need a first-run permission prompt
  - Sound effects playback call — WAV files work everywhere, just the playback API differs
- **Recommended approach**: Create a `platform/` module with `windows.py` and `macos.py` behind a common interface (`play_sound()`, `set_app_id()`, permission checks). Keep one codebase, two build configs (PyInstaller for Windows, py2app for Mac)
- **Hardest part**: macOS Accessibility permission UX — users must manually grant permission in System Settings for hotkeys and simulated typing to work. Testing will also be painful (need a Mac environment)
- **Not prioritized yet** — notes for future planning

## Abandoned Work
- **LLM formatting commands** — tried Qwen2.5 0.5B-7B for voice formatting commands (bullets, numbered lists, scratch that). Generic models can't reliably interpret these. Grammar/punctuation cleanup was re-added without formatting commands.
- **pywhispercpp (whisper.cpp)** — tried for Vulkan GPU support, reverted because CPU performance was ~2x slower than faster-whisper.
