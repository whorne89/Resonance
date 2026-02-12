# Resonance - Claude Code Memory

## Project Overview
Resonance is a Windows voice-to-text desktop application that uses Whisper (via faster-whisper) for speech recognition. It runs as a system tray application — hold a hotkey to record, release to transcribe, and the text is typed into whatever window is focused.

## Tech Stack
- **GUI**: PySide6 (Qt for Python)
- **Audio**: sounddevice
- **Transcription**: faster-whisper (Whisper model via HuggingFace)
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
- **No PyInstaller bundling currently** — PyInstaller dependencies were removed. The app runs directly as a Python script.

## Transcription Flow
1. User holds hotkey -> AudioRecorder captures audio
2. User releases hotkey -> Audio sent to TranscriptionWorker (QThread)
3. Worker calls Transcriber.transcribe() -> returns text
4. VTTApplication.on_transcription_complete() applies dictionary replacements
5. KeyboardTyper.type_text() outputs to active window

## Config Location
Settings stored at `<app_root>/.resonance/settings.json`

## Common Gotchas
- `get_app_data_path()` in resource_path.py determines where all persistent data goes (models, config, logs)
- Logger must import from resource_path to stay consistent with the data path
- TranscriptionWorker runs in QThread — signals connect back to main thread
- Settings dialog creates a fresh instance each time it's opened (not reused)
