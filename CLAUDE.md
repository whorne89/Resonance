# Resonance - Claude Code Memory

## Project Overview
Resonance is a Windows voice-to-text desktop application that uses Whisper (via faster-whisper) for speech recognition. It runs as a system tray application — hold a hotkey to record, release to transcribe, and the text is typed into whatever window is focused.

## Tech Stack
- **Python 3.12** — pinned via `.python-version`; uv manages the venv
- **GUI**: PySide6 (Qt for Python)
- **Audio**: sounddevice (recording), winsound (notification tones)
- **Transcription**: faster-whisper (CTranslate2 backend, CPU only)
- **OCR**: winocr (Windows native OCR), mss (screenshot capture)
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
    transcriber.py           - Whisper model loading and transcription (+ partial download cleanup)
    keyboard_typer.py        - Keyboard input simulation (type or paste)
    hotkey_manager.py        - Global hotkey registration (pynput)
    dictionary.py            - Post-transcription word replacement (exact + fuzzy)
    post_processor.py        - LLM post-processing via llama-server (grammar/punctuation/filler cleanup)
    screen_context.py        - OCR screen capture, app-type detection, name extraction
    learning_engine.py       - Self-learning per-app profiles (vocabulary, style metrics)
    sound_effects.py         - Notification tones via winsound (WAV files)
    updater.py               - Auto-updater: GitHub Releases check, download, batch-script self-update
  gui/
    system_tray.py           - System tray icon with context menu
    settings_dialog.py       - Settings UI (hotkey, model, audio, typing, dictionary, updates)
    dictionary_dialog.py     - Custom dictionary editor UI
    recording_overlay.py     - Floating pill overlay with waveform visualization
    update_toast.py          - Interactive update toast with Yes/No buttons + auto-dismiss
  utils/
    config.py                - ConfigManager (JSON settings)
    resource_path.py         - Path resolution (app data, resources)
    logger.py                - Logging with file rotation
  resources/
    icons/                   - Tray icons (idle, recording)
    sounds/                  - Piano tone WAV files (start/stop)
resonance.spec               - PyInstaller build spec (--onedir)
```

## Key Design Decisions
- **App data stored relative to application directory** (not user home). Data lives in `<app_root>/.resonance/` so models, logs, and config stay on the same drive as the app.
- **Custom dictionary** for post-transcription word replacement. Stored in config under `dictionary.replacements`. Case-insensitive matching, applied via `DictionaryProcessor.apply()`.
- **Recording overlay** — frameless QPainter pill widget, always-on-top, click-through (`WindowTransparentForInput`). Shows pulsing red dot + live waveform bars during recording, animated blue dots during processing.
- **Sound effects** — generated as WAV files in `.resonance/sounds/`, played via `winsound.PlaySound(SND_FILENAME | SND_ASYNC)`. Users can drop custom `start.wav`/`stop.wav` to override defaults. Using winsound avoids conflicts with sounddevice recording.
- **Thread-safe hotkey handling** — hotkey callbacks emit Qt signals (`_hotkey_pressed`/`_hotkey_released`) to marshal execution from pynput background threads to the main Qt thread.
- **CPU only, GPU scrapped** — see GPU section below.

## Versioning
- **Single source of truth**: `version` field in `pyproject.toml` (currently 3.1.6)
- About dialog reads via `importlib.metadata.version('resonance')` — never hardcode version strings
- Package must be installed in editable mode (`uv pip install -e .`) for importlib.metadata to work
- In bundled EXE, version lives in `_internal/resonance-X.Y.Z.dist-info/` — only ONE such directory must exist or `importlib.metadata` picks the wrong version (alphabetically first)

## Transcription Flow
1. User holds hotkey → start tone plays → AudioRecorder captures audio → overlay shows recording state
1a. If OCR enabled, ScreenContextEngine.capture() fires in background thread (~56ms) — captures window, runs OCR, detects app type, extracts proper nouns. If self-learning is also enabled, LearningEngine.learn_from_context() updates per-app profiles with vocabulary and style metrics
2. User releases hotkey → stop tone plays → audio sent to TranscriptionWorker (QThread) → overlay shows processing state
3. Worker calls Transcriber.transcribe(initial_prompt=ocr_names) → PostProcessor.process(system_prompt=app_type_prompt) (if enabled) → structural formatting (chat/email) → returns text
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

### PySide6 Threading — Critical
- **`QueuedConnection` on plain Python functions does NOT work.** There is no receiver QObject to determine the target thread, so callbacks silently run on the worker thread regardless. Qt widgets created/modified from non-GUI threads crash or silently fail.
- **Fix: relay signals through QObject instances.** Worker signal → QObject relay signal → callback. `VTTApplication` (a QObject) has relay signals (`_relay_model_loaded`, `_relay_update`, `_relay_dl_progress`, etc.) that re-emit on the main thread. `AutoConnection` works correctly when both sender and receiver are QObjects.
- **In dialogs/widgets**, convert closures to bound methods on the QWidget/QDialog (which is a QObject). E.g. `worker.signal.connect(self._on_result)` instead of `worker.signal.connect(lambda: ...)`.
- **Symptom of wrong thread**: toast/widget "shows" (logs say success) but is invisible, or app crashes with segfault on signal emit.

### Windows Batch Script Gotchas
- **`for /D %%d in ("path\with\*.glob")` does NOT expand wildcards** — quotes make the pattern literal. Fix: `pushd "path\with"` then `for /D %%d in (*.glob)` with an unquoted relative pattern, then `popd`.
- **`DETACHED_PROCESS`** flag for `subprocess.Popen` silently fails on some Windows machines. Use `CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW` instead.
- Write batch scripts and extracted update files to **system temp** (`tempfile.gettempdir()`), not inside the app directory.

## Post-Processing
- **Backend**: llama-server (llama.cpp) with Qwen 2.5 1.5B Instruct GGUF (q4_k_m, ~1.1 GB)
- **Scope**: Grammar, capitalization, punctuation (periods, commas, question marks, quotation marks), contractions, sentence breaks, filler word removal (um, uh), and stutter/repeat cleanup
- **Prompt philosophy**: Conservative — keep every word the speaker said, only fix formatting. Do NOT summarize, shorten, or rephrase. Three explicit rules: (1) remove um/uh/stutters, (2) fix capitalization + punctuation, (3) fix grammar.
- **Hallucination guards**: Five-layer system in `_process_via_api()`: (1) filler-only input returns empty, (2) length guard rejects output >1.5x input, (3) answer-pattern guard, (4) question-answer guard, (5) comma-spam guard (rejects output with >words/3 commas)
- **Lifecycle**: Tied to settings checkbox — created when ON, `.shutdown()` kills llama-server when OFF
- **Lazy loading**: Server subprocess starts on first `.process()` call, not at toggle-on
- **Pipeline**: Whisper → PostProcessor.process() → DictionaryProcessor.apply() → KeyboardTyper
- **Files**: llama-server.exe in `.resonance/bin/`, GGUF model in `.resonance/models/postproc-gguf/`

## Screen Context (OCR)
- **Backend**: winocr (Windows native OCR engine), mss (screenshot capture)
- **Scope**: Captures active window text on hotkey press to (1) extract proper nouns for Whisper vocabulary hints via `initial_prompt`, (2) detect app type (CHAT, EMAIL, CODE, DOCUMENT, GENERAL) for format-specific post-processing prompts
- **Architecture**: `ScreenContextEngine` in `core/screen_context.py`. Runs in background thread during recording (~56ms total). Returns `ScreenContext` dataclass with raw_text, app_type, proper_nouns, window_title
- **App detection**: Heuristic keyword matching on window title + OCR text (e.g. "Discord" → CHAT, "Outlook" → EMAIL, "Visual Studio" → CODE, "cmd.exe" → TERMINAL)
- **App types**: CHAT, EMAIL, CODE, TERMINAL, DOCUMENT, GENERAL — each has a dedicated system prompt
- **Prompts**: Five app-type-specific system prompts (CHAT, EMAIL, CODE, TERMINAL, DOCUMENT) as module-level constants in screen_context.py
- **Structural formatting**: Python handles deterministic fixes — chat trailing period removal
- **Dependency**: Requires post-processing to be enabled (OCR feeds into both Whisper and Qwen)
- **Graceful fallback**: If OCR fails for any reason, `capture()` returns None and transcription proceeds without context

## Self-Learning Recognition
- **Engine**: `LearningEngine` in `core/learning_engine.py` — passively builds per-app profiles from OCR screen data
- **What it learns**: Per-app vocabulary (proper nouns seen on screen), style metrics (message length, capitalization ratio, punctuation ratio, formality score, abbreviation count), and app type with increasing confidence
- **Pipeline integration**: Learned vocabulary is merged with OCR proper nouns and fed to Whisper's `initial_prompt`. Style hints (from `build_style_prompt_suffix`) are appended to the post-processing system prompt. Both are wired in `start_transcription()` → `TranscriptionWorker`
- **App key normalization**: Extracts stable identifiers from volatile window titles — "Discord - #general" and "Discord - #random" map to the same `discord` key. Detects web apps inside browsers (e.g. "Outlook - Google Chrome" → `outlook`)
- **KNOWN_APPS**: Dict mapping name fragments to (app_key, display_name, app_type) — 30+ apps across chat, email, code, terminal, document categories
- **Style merging**: Uses exponential moving average (EMA, alpha=0.3) so profiles stabilize over time but adapt. Needs ≥3 samples before style hints are used
- **Storage**: JSON at `<app_root>/.resonance/learning/app_profiles.json` — separate from settings to avoid bloat
- **Limits**: Max 100 vocabulary per app, max 200 profiles total, stale profiles (90 days unused) auto-cleaned
- **Privacy**: Never stores raw OCR text or conversations — only app identifiers, proper noun vocabulary, and aggregate statistical metrics
- **Dependency chain**: Requires both post-processing AND OSR to be enabled (settings UI enforces this with grayed-out toggles)
- **Thread safety**: All mutations through `threading.Lock()` (same pattern as PostProcessor)
- **Overlay badges**: OSR-only shows generic type ("Chat", "Email"); self-learning shows specific app name ("Discord", "Outlook"). Hidden for "General" type

## Portable EXE (PyInstaller)
- **Build**: `pyinstaller resonance.spec -y` produces `dist/Resonance/Resonance.exe` (`--onedir`)
- **Spec** (`resonance.spec`): entry `src/main.py`, pathex `src/`, bundles icons + sounds, `collect_all('faster_whisper')` + `collect_all('ctranslate2')`, `copy_metadata('resonance')`, hidden imports for sounddevice/pynput, `console=False`
- **Detection**: `is_bundled()` checks `hasattr(sys, '_MEIPASS')`. `sys.executable` = the EXE path, `sys._MEIPASS` = temp extraction dir
- **SSL fix**: Spec force-bundles Python's own `libssl-3.dll`/`libcrypto-3.dll` to avoid PySide6 OpenSSL DLL mismatch
- **stderr redirect**: PyInstaller windowed mode sets `sys.stderr = None`. `main.py` redirects to devnull to prevent tqdm/huggingface_hub crashes during model download
- **Build command**: `uv pip install -e . --python .venv/Scripts/python.exe && .venv/Scripts/pyinstaller.exe resonance.spec -y`

## Auto-Updater
- **Check**: `UpdateChecker` in `core/updater.py` hits GitHub Releases API (`/repos/whorne89/Resonance/releases/latest`), compares versions via `packaging.version.Version`, finds `.zip` asset
- **Startup flow**: `QTimer.singleShot(8000, _start_update_check)` in `main()` → `_UpdateCheckWorker` runs in QThread → on update found, shows `UpdateToast` (interactive Yes/No, 10s auto-dismiss)
- **Download**: On accept, shows `_UpdateDownloadDialog` (progress bar) → downloads ZIP to `.resonance/updates/`
- **Apply (EXE only)**: `apply_update()` extracts ZIP to system temp, writes `_resonance_update.bat` that: waits for PID exit → `pushd _internal` + delete old `resonance-*.dist-info` via `for /D` → `popd` → `xcopy /E /Y /Q` new files → `start` EXE → cleanup temp + ZIP + self-delete
- **Source installs**: Shows "Run: git pull && uv sync" message instead of download
- **Settings**: "Check for Updates" button + version label in updates group. Uses `_UpdateCheckWorker` / `_UpdateDownloadDialog` with bound methods (not closures) for thread safety
- **Signal relay**: All worker signals route through `VTTApplication` relay signals to ensure callbacks run on the main GUI thread (see PySide6 Threading gotcha)
- **GitHub Release setup**: Tag with `vX.Y.Z`, attach `Resonance.zip` asset. The ZIP's `_internal/resonance-X.Y.Z.dist-info/` must match the tag version — mismatched versions cause infinite update loops
- **Testing**: Must build separate ZIPs for each version. A "dummy" test release reusing the same ZIP will loop because `importlib.metadata.version()` reads the dist-info from inside the ZIP, not the GitHub tag

## Download Auto-Recovery
- **Partial download cleanup**: `transcriber.clean_partial_download(model_size)` detects `.incomplete` blobs or missing `model.bin` in HF cache snapshots → `shutil.rmtree()` the entire model cache dir
- **Called at**: startup in `main()` before `is_model_downloaded()` check, and in `_DownloadWorker.run()` before `snapshot_download()`

## UI Components (v3.0)
- **ToastNotification**: Dark pill at bottom-right, supports multi-line messages + bold details section. "Resonance" header at 15px bold. `WindowTransparentForInput` (click-through).
- **UpdateToast**: Same visual style as ToastNotification but NOT click-through — has interactive Yes/No buttons. 10-second auto-dismiss timer. Signals: `accepted()`, `dismissed()`.
- **ClipboardToast**: Centered pill at bottom (240×52), shows "Text entered" (clipboard) or "Typing" (char-by-char) at 24px
- **RecordingOverlay**: Pill at bottom-center with waveform. During recording: stacked feature badges (e.g. "Learning OSR: ON", "Post-Processing: ON"). During typing/pasted: detected app badge + estimated accuracy badge. Hidden for "General" type
- **AboutDialog**: RoundedDialog with 28px title, subtitle, description mentioning Whisper + Qwen, author, version from importlib.metadata
- **Startup toast**: Shows hotkey, model name, OSR status (with learning indicator), post-processing status, and entry method (details in bold)
- **Settings**: Dependency-chained toggles (PP → OSR → Self-Learning) with grayed-out labels showing requirements. Learning stats cards: Apps Learned, Words Learned, Top App, Avg Confidence. Updates group: version label, Check for Updates button, Download and Install button (EXE only)

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
