# Resonance

A local voice-to-text dictation application for Windows using OpenAI Whisper with AI post-processing from Qwen 2.5. Type with your voice in any application - browsers, chat windows, code editors, and more.

## Features

- **Push-to-talk recording**: Press and hold a hotkey to record, release to transcribe
- **System-wide input**: Works in any application (browsers, editors, chat apps, Claude, etc.)
- **Local processing**: Uses Whisper AI running locally on your computer (no cloud, no API costs)
- **Fast transcription**: Uses faster-whisper (4x faster than standard Whisper)
- **AI post-processing**: Optional cleanup using a local Qwen 2.5 language model — fixes grammar, capitalization, punctuation, contractions, quotations, and sentence breaks; removes filler words (um, uh) and stutters
- **Screen context (OCR)**: Captures the active window to improve name accuracy and adapt formatting for chat, email, code, and documents
- **Custom dictionary**: Post-transcription word replacement with exact and fuzzy matching
- **Recording overlay**: Floating pill widget with live waveform visualization and feature badges
- **Sound effects**: Audible start/stop tones with custom sound support
- **Simple interface**: Dark-themed system tray application with toast notifications
- **Configurable**: Customize hotkey, model size, audio device, and typing method
- **Automatic model download**: Downloads the speech model on first launch with progress animation

## Requirements

- **Windows 10 or 11**
- Python 3.12 (managed via uv)
- Microphone

## Installation

### Option 1: Run from Source (Recommended)

1. Clone or download this repository
2. **Install uv** (if not already installed):
   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```
3. **Run the application:** Double-click `START RESONANCE.bat`

### Option 2: Build Executable

1. Clone or download this repository
2. Install `uv` (see step 2 above)
3. Double-click `BUILD RESONANCE.bat`
4. The executable will be created at `dist\Resonance\Resonance.exe`
5. Copy the entire `dist\Resonance` folder anywhere - no installation needed!

## Usage

1. Launch the application (system tray icon will appear)
2. On first launch, the Balanced model (~140 MB) downloads automatically
3. Open any application where you want to type
4. **Press and hold `Ctrl+Alt`** (default hotkey)
5. Speak into your microphone
6. **Release the hotkey** to transcribe
7. Text will be automatically typed into the active window

## Configuration

Right-click the system tray icon and select **Settings** to configure:

- **Hotkey**: Change the push-to-talk keyboard shortcut
- **Quality**: Choose a Whisper model for speech recognition
  - **Fastest**: Whisper Tiny (~70 MB), sub-second
  - **Balanced**: Whisper Base (~140 MB), sub-second *(default)*
  - **Accurate**: Whisper Small (~500 MB), ~2s
  - **Precision**: Whisper Medium (~1.5 GB), ~5s
- **Post-Processing (AI)**: Enable/disable AI-powered transcription cleanup using Qwen 2.5 1.5B (downloaded automatically, runs locally via llama.cpp)
- **Screen Context (OCR)**: Enable OCR-based screen capture for app-aware formatting and name accuracy (requires Post-Processing)
- **Audio Device**: Select which microphone to use
- **Entry Method**: Choose between clipboard paste or character-by-character typing
- **Custom Dictionary**: Add word replacements applied after transcription
- **Usage Statistics**: Track words dictated, transcriptions, time saved, and more
- **Bug Report**: Submit a pre-filled GitHub issue with system info and recent logs directly from Settings

## Technical Details

### Technology Stack

- **Python 3.12** (pinned via `.python-version`, managed by uv)
- **PySide6**: GUI framework (system tray, settings, overlays, toast notifications)
- **sounddevice**: Audio recording
- **faster-whisper**: Speech recognition (CTranslate2 backend, CPU-optimized)
- **llama.cpp** (llama-server): Local inference server for post-processing
- **Qwen 2.5 1.5B Instruct** (GGUF Q4_K_M): Language model for transcription cleanup
- **winocr**: Windows native OCR for screen context capture
- **mss**: Screenshot capture for OCR
- **pynput**: Global hotkeys and keyboard simulation
- **pyperclip**: Clipboard-based text entry

### How It Works

1. Global hotkey listener detects when you press/release the configured hotkey
2. Audio is recorded from your microphone at 16kHz (Whisper's native sample rate)
3. If screen context is enabled, OCR captures the active window in a background thread during recording (~56ms)
4. When you release the hotkey, the audio is sent to faster-whisper for transcription (OCR-detected names are passed as vocabulary hints)
5. If post-processing is enabled, the text is cleaned up by Qwen 2.5 via a local llama-server instance with an app-type-specific prompt (chat, email, code, or document)
6. Custom dictionary replacements are applied
7. Text is typed into the currently focused window via clipboard paste or keyboard simulation

## Troubleshooting

### "uv is not recognized" error

Make sure `uv` is installed (see Installation step 2) and restart your terminal/command prompt after installation to refresh your PATH.

### OneDrive/Cloud Sync Error

The batch files use a local cache (`UV_CACHE_DIR`) to avoid OneDrive hardlink issues. If you still see hardlink errors, your uv cache may be in an OneDrive-synced AppData folder.

**Solution:** Edit the batch files and change `uv sync --no-audit` to `uv sync --no-audit --link-mode=copy`

### No transcription output

- Check that your microphone is working and selected in Settings
- Ensure you're speaking clearly and loudly enough
- Try a larger model size for better accuracy

### Hotkey not working

- Check for conflicts with other applications using the same hotkey
- Try changing to a different hotkey combination in Settings
- Some applications with anti-cheat or security features may block global hotkeys

### Text not typing into application

- Some security-focused applications may block simulated keyboard input
- Try switching to clipboard paste in Settings

### First run is slow

- The Whisper model downloads automatically on first launch (~140 MB for the default Balanced model)
- Models are cached locally, subsequent runs start instantly

## License

MIT License

## Roadmap

- **In-app updater** — Check GitHub for new versions from Settings. Source installs update via `git pull` + `uv sync`; future exe builds will download from GitHub Releases. Version check logic is shared between both.
- **Light / Dark / System theme** — Toggle between light mode, dark mode, or follow the system setting. Each can be selected independently in Settings.
- ~~**On-screen recognition (OCR)**~~ — Shipped in v2.3.0 as Screen Context.
- **macOS support** — Single Python codebase for Windows and Mac with platform-specific abstractions for sound, hotkeys, and typing.

## Changelog

### v2.2.1
- **Bug report button**: Settings dialog includes a "Report Bug..." button that opens a pre-filled GitHub issue with system info and recent logs

### v2.2.0
- **Scrollable settings dialog**: Settings now scroll vertically on small screens with fixed Save/Cancel buttons at bottom
- **Startup model download**: Automatically downloads the speech model on first launch with animated progress toast; hotkey is disabled until download completes
- **Default model changed**: New installations default to Balanced (base, ~140 MB) instead of Accurate (small, ~500 MB) for faster first-run
- **No speech detected**: Recording overlay shows "No speech detected" in red when transcription returns empty
- **Scroll wheel fix**: Mouse wheel no longer accidentally changes dropdown selections while scrolling settings
- **Improved scrollbar styling**: Thinner, transparent scrollbar that blends with the dark theme

### v2.1.0
- **AI post-processing**: Local Qwen 2.5 model cleans up grammar, punctuation, capitalization, contractions, quotations, sentence breaks, filler words, and stutters
- **Recording overlay badges**: Shows active features (Post-Processing: ON) above the recording pill
- **Startup toast**: Displays model, post-processing status, and entry method on launch
- **Clipboard/typing toast**: Visual confirmation showing "Text entered" or "Typing" after transcription
- **Overlay typing states**: Green "Complete" and "Text Entered" states, animated dots during character-by-character output
- **Usage statistics**: Dashboard with 8 stat cards (words dictated, transcriptions, time saved, avg WPM, and more)

### v2.0.0
- Dark theme with rounded frameless dialogs
- Model download progress UI in settings
- Recording overlay with live waveform visualization
- Custom dictionary with fuzzy matching
- Sound effects (start/stop tones) with custom WAV support
- Thread-safe hotkey handling

## Credits

Built with:

- [OpenAI Whisper](https://github.com/openai/whisper)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- [Qwen 2.5](https://github.com/QwenLM/Qwen2.5) (post-processing)
- [llama.cpp](https://github.com/ggml-org/llama.cpp) (local inference)
- [PySide6](https://www.qt.io/qt-for-python)
