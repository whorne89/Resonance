# Resonance - Claude Code Memory

## Project Overview
Resonance is a Windows voice-to-text desktop application that uses Whisper (via faster-whisper) for speech recognition. It runs as a system tray application — hold a hotkey to record, release to transcribe, and the text is typed into whatever window is focused.

## Tech Stack
- **Python 3.12** — pinned via `.python-version`; uv manages the venv
- **GUI**: PySide6 (Qt for Python)
- **Audio**: sounddevice
- **Transcription**: faster-whisper (CTranslate2 backend, CPU only)
- **Post-processing**: llama-server (llama.cpp) with Qwen2.5-0.5B-Instruct Q4_K_M
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
    post_processor.py        - LLM post-processing (llama-server / onnx backends)
    keyboard_typer.py        - Keyboard input simulation (type or paste)
    hotkey_manager.py        - Global hotkey registration (pynput)
  gui/
    system_tray.py           - System tray icon with context menu
    settings_dialog.py       - Settings UI (hotkey, model, audio, typing, dictionary, post-processing)
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
- **No PyInstaller bundling currently** — the app runs directly as a Python script.
- **CPU only, GPU scrapped** — see GPU section below.

## Versioning
- **Single source of truth**: `version` field in `pyproject.toml` (currently 1.2.0)
- About dialog reads via `importlib.metadata.version('resonance')` — never hardcode version strings
- Package must be installed in editable mode (`uv pip install -e .`) for importlib.metadata to work

## Transcription Flow
1. User holds hotkey -> AudioRecorder captures audio
2. User releases hotkey -> Audio sent to TranscriptionWorker (QThread)
3. Worker calls Transcriber.transcribe() -> returns raw text
4. Worker calls PostProcessor.process() -> fixes grammar/formatting (if enabled)
5. VTTApplication.on_transcription_complete() applies dictionary replacements
6. KeyboardTyper.type_text() outputs to active window

## Whisper Models
- Dropdown uses display-name -> model-ID mapping with `QComboBox.addItem(name, userData=id)`
- distil-whisper models use full HF repo IDs: `Systran/faster-distil-whisper-large-v3`
- HF cache dir converts `/` -> `--`: `models--Systran--faster-distil-whisper-large-v3`
- `transcriber.is_model_downloaded()` handles both short names (`small`) and full repo IDs
- **Model benchmarks (5s audio, Ryzen 3700X CPU)**:
  - tiny: sub-second, decent accuracy, inconsistent punctuation
  - base: sub-second, good accuracy
  - small: ~2s, good accuracy
  - distil-small.en: ~2s, good accuracy, English-optimized
  - distil-large-v3: noticeably slower than distil-small, not worth the latency trade-off for dictation
- **Current strategy**: tiny model + CPU post-processing for grammar/punctuation cleanup. Tiny is extremely fast and post-processing can fix accuracy gaps.

## GPU — Scrapped
- **CUDA**: ruled out — CTranslate2 needs exact CUDA 12.x DLLs (cublas64_12.dll), user has CUDA 13.1. Not portable.
- **Vulkan via pywhispercpp**: tried and reverted — pywhispercpp CPU is ~2x slower than faster-whisper (4.5s vs 2.2s for 5s audio). Unacceptable latency for dictation.
- **Decision**: CPU-only with faster-whisper. GPU not needed — tiny model is already sub-second.

## Post-Processing
- **Backend**: llama-server (llama.cpp binary) managing Qwen2.5-0.5B-Instruct Q4_K_M GGUF model
- **Alternative backend**: onnxruntime-genai (pure Python, slower but simpler install)
- **Benchmarks (Ryzen 3700X CPU)**: llama-server 0.34s/sample (39.8 tok/s), onnx 0.99s/sample (16.2 tok/s)
- **Server startup**: ~1s one-time; stays loaded in memory between transcriptions
- **PostProcessor class**: `src/core/post_processor.py` — lazy-loads model, thread-safe, graceful fallback
- **Config**: `post_processing.enabled` (default False), `post_processing.backend` (default "llama-server")
- **Model storage**: GGUF in `.resonance/models/postproc-gguf/`, binary in `.resonance/bin/`
- **Settings UI**: "Post-Processing (Experimental)" group with enable checkbox and download button
- **Prompt tuning needed**: formatting commands (bullet, new line, scratch that) work partially; capitalization inconsistent

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
- **llama-server subprocess**: must use absolute paths on Windows; needs all DLLs from the zip (ggml-*.dll, llama.dll, etc.)
- **onnxruntime-genai v0.12 API**: no `input_ids` on params; use `generator.append_tokens()` instead; `apply_chat_template` takes JSON string

## Abandoned Work
- **`feat/post-processing` branch** — grammar correction via llama-cpp-python; parked due to distribution complexity (no pre-built Python 3.12 wheels, CUDA build issues). Code preserved on branch.
- **pywhispercpp (whisper.cpp)** — tried for Vulkan GPU support, reverted because CPU performance was ~2x slower than faster-whisper.
