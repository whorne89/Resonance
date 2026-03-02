# Resonance

A local voice-to-text dictation application for Windows using OpenAI Whisper with AI post-processing from Qwen 2.5. Type with your voice in any application - browsers, chat windows, code editors, and more.

## Features

- **Push-to-talk recording**: Press and hold a hotkey to record, release to transcribe
- **System-wide input**: Works in any application (browsers, editors, chat apps, Claude, etc.)
- **Local processing**: Uses Whisper AI running locally on your computer (no cloud, no API costs)
- **Fast transcription**: Uses faster-whisper (4x faster than standard Whisper)
- **AI post-processing**: Optional cleanup using a local Qwen 2.5 language model — fixes grammar, capitalization, punctuation, contractions, quotations, and sentence breaks; removes filler words (um, uh) and stutters
- **On-Screen Recognition (OSR)**: Captures the active window via OCR to improve name accuracy and adapt formatting for chat, email, code, terminal, and documents
- **Self-learning recognition**: Passively builds per-app profiles over time — learns vocabulary, communication style, and app types so transcription accuracy improves the more you use it
- **Estimated accuracy**: Displays Whisper's confidence score on each transcription with detected app context
- **Custom dictionary**: Post-transcription word replacement with exact and fuzzy matching
- **Recording overlay**: Floating pill widget with live waveform visualization, feature badges, and app detection
- **Sound effects**: Audible start/stop tones with custom sound support
- **Simple interface**: Dark-themed system tray application with toast notifications
- **Configurable**: Customize hotkey, model size, audio device, and typing method
- **Automatic model download**: Downloads the speech model on first launch with progress animation

## Requirements

- **Windows 10 or 11**
- Python 3.12 (managed via uv)
- Microphone

## Installation

1. Clone or download this repository
2. **Install uv** (if not already installed):
   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```
3. **Run the application:** Double-click `START RESONANCE.bat`

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
- **On-Screen Recognition (OSR)**: Enable OCR-based screen capture for app-aware formatting and name accuracy (requires Post-Processing)
- **Self-Learning Recognition**: Enable persistent per-app learning that improves over time (requires OSR)
- **Audio Device**: Select which microphone to use (WASAPI devices only for clean device list)
- **Entry Method**: Choose between clipboard paste or character-by-character typing
- **Custom Dictionary**: Add word replacements applied after transcription
- **Usage Statistics**: Track words dictated, transcriptions, time saved, and more
- **Learning Statistics**: Apps learned, words learned, top app, and average confidence
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
3. If OSR is enabled, OCR captures the active window in a background thread during recording (~56ms). If self-learning is also enabled, the captured data updates per-app vocabulary and style profiles
4. When you release the hotkey, the audio is sent to faster-whisper for transcription (OCR-detected names are passed as vocabulary hints)
5. If post-processing is enabled, the text is cleaned up by Qwen 2.5 via a local llama-server instance with an app-type-specific prompt (chat, email, code, terminal, or document)
6. Custom dictionary replacements are applied
7. Text is typed into the currently focused window via clipboard paste or keyboard simulation

### Feature Layers

Each feature builds on the previous one. Here's what changes at each level, using real examples of what you'd get if you said the same thing out loud.

#### Whisper Only (all features off)

Raw transcription from Whisper. It catches most words accurately and strips obvious filler sounds (um, uh), but punctuation, capitalization, and grammar are inconsistent.

| You say | You get |
|---------|---------|
| "yeah i was talking to jake about the uh the kubernetes deployment and he said its basically done" | `yeah I was talking to Jake about the the Kubernetes deployment and he said its basically done` |
| "hey sarah i wanted to follow up on the meeting about the robinson account" | `hey Sarah I wanted to follow up on the meeting about the Robinson account` |
| "can you check if the env variable for the redis connection string is set" | `can you check if the env variable for the Redis connection string is set` |
| "thanks for getting back to me so quickly i really appreciate it talk to you soon" | `thanks for getting back to me so quickly I really appreciate it talk to you soon` |

Whisper strips "uh" and "um" but misses stutters ("the the"), drops punctuation, and has inconsistent capitalization ("i" vs "I"). Every app gets the same raw output.

#### + Post-Processing

Enables the local Qwen 2.5 language model to clean up Whisper's output. Fixes grammar, capitalization, punctuation, contractions, stutters, and sentence breaks.

| You say | Whisper only | + Post-Processing |
|---------|-------------|-------------------|
| "yeah i was talking to jake about the uh the kubernetes deployment and he said its basically done" | `yeah I was talking to Jake about the the Kubernetes deployment and he said its basically done` | `Yeah, I was talking to Jake about the Kubernetes deployment and he said it's basically done.` |
| "hey sarah i wanted to follow up on the meeting about the robinson account" | `hey Sarah I wanted to follow up on the meeting about the Robinson account` | `Hey Sarah, I wanted to follow up on the meeting about the Robinson account.` |
| "thanks for getting back to me so quickly i really appreciate it talk to you soon" | `thanks for getting back to me so quickly I really appreciate it talk to you soon` | `Thanks for getting back to me so quickly. I really appreciate it. Talk to you soon.` |
| "the the project is almost done i think we should uh deploy it tomorrow" | `the the project is almost done I think we should deploy it tomorrow` | `The project is almost done. I think we should deploy it tomorrow.` |

Stutter ("the the") removed, contractions fixed ("its" to "it's"), sentence breaks added, proper punctuation and capitalization throughout. However, the same formal style is applied everywhere — a Discord message gets the same treatment as an email.

#### + On-Screen Recognition (OSR)

OCR captures your active window during recording. Two things improve:

1. **Name accuracy**: Proper nouns visible on screen (colleague names, project names, technical terms) are fed to Whisper as vocabulary hints, so it spells them correctly
2. **App-aware formatting**: The post-processing prompt changes based on what app you're in

| App type | What changes |
|----------|-------------|
| **Chat** (Discord, Slack, Teams) | Keeps slang (lol, lmao, tbh, ngl), preserves "like", lowercase start, no trailing period, keeps casual emphasis (yeah yeah, fr fr), preserves informal contractions (tryna, gonna, wanna) |
| **Email** (Outlook, Gmail) | Professional tone, complete sentences, proper greetings preserved |
| **Code** (VS Code, PyCharm) | Preserves camelCase, snake_case, technical terms, file extensions |
| **Terminal** (PowerShell, cmd) | Preserves command names, flags, paths, technical terms |
| **Document** (Word, Notion) | Well-structured sentences, breaks run-on speech into clear paragraphs |

Example — same sentence, different apps:

| You say | Post-Processing only | + OSR in Discord (Chat) | + OSR in Outlook (Email) |
|---------|---------------------|------------------------|--------------------------|
| "yeah ngl i think we should just push it to tomorrow tbh" | `Yeah, I think we should just push it to tomorrow.` | `yeah ngl I think we should just push it to tomorrow tbh` | `Yeah, I think we should just push it to tomorrow.` |
| "hey can you send me that report when you get a chance" | `Hey, can you send me that report when you get a chance?` | `hey can you send me that report when you get a chance?` | `Hey, can you send me that report when you get a chance?` |

The Chat prompt keeps the message casual — slang stays, lowercase start, no unnecessary period. The Email prompt keeps it professional. Without OSR, everything gets the same generic treatment.

**Name accuracy example**: If your coworker "Priya Raghavan" is visible in a Slack thread, OSR feeds that name to Whisper. Without it, Whisper might transcribe "Priya Ragavan" or "Priya Raghaven". With OSR, the correct spelling is hinted.

#### + Self-Learning

Builds persistent per-app profiles that improve over time. Two things are added on top of OSR:

1. **Vocabulary from past sessions**: Names and terms you've encountered before in an app are used as Whisper hints even when they aren't visible on the current screen. If "Priya Raghavan" appeared in Slack last week, the learning engine remembers and hints it for future transcriptions in Slack
2. **Style adaptation**: After 3+ sessions in an app, the engine learns communication patterns (formality level, punctuation habits, capitalization style) and adjusts the post-processing prompt to match

| Feature | OSR only | + Self-Learning |
|---------|---------|-----------------|
| Vocabulary hints | Only names visible on screen right now | Names from screen + all names seen in this app before |
| Style prompt | Fixed per app type | Adapts to observed patterns (casual vs formal, punctuation density, etc.) |
| Overlay badge | Generic type ("Chat", "Email") | Specific app name ("Discord", "Outlook") |
| Persistence | None — starts fresh each session | Profiles saved to disk, improve across sessions |

**Practical example**: You use Slack daily with teammates named "Dmitri", "Xiaowen", and "Kayleigh". After a few sessions with self-learning on, these names are in your Slack vocabulary profile. Even when none of them are visible on screen, Whisper gets them as hints and spells them correctly. Without self-learning, Whisper would only get hints for names currently visible on the screen.

#### Summary

| Layer | What it adds | Requires |
|-------|-------------|----------|
| **Whisper only** | Raw speech-to-text | Nothing |
| **+ Post-Processing** | Grammar, punctuation, capitalization, stutter removal, sentence breaks | Qwen 2.5 model (~1.1 GB download) |
| **+ OSR** | App-aware formatting, name accuracy from screen | Post-Processing |
| **+ Self-Learning** | Persistent vocabulary, style adaptation, improves over time | OSR |

## Troubleshooting

### "uv is not recognized" error

Make sure `uv` is installed (see Installation step 2) and restart your terminal/command prompt after installation to refresh your PATH.

### OneDrive/Cloud Sync Error

The startup batch file uses a local cache (`UV_CACHE_DIR`) to avoid OneDrive hardlink issues. If you still see hardlink errors, your uv cache may be in an OneDrive-synced AppData folder.

**Solution:** Edit `START RESONANCE.bat` and change `uv sync --no-audit` to `uv sync --no-audit --link-mode=copy`

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
- ~~**On-screen recognition (OCR)**~~ — Shipped in v3.0.0.
- ~~**Self-learning recognition**~~ — Shipped in v3.0.0.
- **macOS support** — Single Python codebase for Windows and Mac with platform-specific abstractions for sound, hotkeys, and typing.

## Changelog

### v3.1.2
- **Fix: model download crash in EXE** — PyInstaller windowed mode sets `sys.stderr` to `None`, causing `tqdm`/`huggingface_hub` to crash with "NoneType has no attribute 'write'" when downloading models from Settings. Fixed by redirecting to devnull
- **Fix: crash on cancelling model download** — Closing or cancelling a download dialog while `snapshot_download()` was running would crash the app. Worker signals are now disconnected before cleanup, and stuck threads are safely detached
- **Fix: model combo not reverting on failed download** — After a failed download, the dropdown stayed on the failed model causing repeated download attempts on Save. Now reverts to the previously saved model
- **Fix: download toast stuck after first-run install** — The "Installing model" toast would not dismiss after the download completed. Now cleanly hides and shows the startup toast
- **Fix: "Learning OSR" badge shown without dependencies** — The overlay badge checked the config flag (default: true) instead of the actual engine instance. Fresh installs showed "Learning OSR" even with post-processing and OSR off. Default changed to false and badge now checks engine state
- **Fix: bundled sounds missing** — PyInstaller spec only bundled icons, not the custom piano tone WAV files. Added `src/resources/sounds/` to the build
- **Fix: SSL DLL mismatch in EXE** — PyInstaller picked up PySide6's OpenSSL DLLs instead of Python's, causing `_ssl` import failures on machines without Python. Spec now force-bundles Python's own `libssl`/`libcrypto` DLLs

### v3.1.1
- **Portable EXE**: Distributable as a single folder — extract the ZIP, double-click `Resonance.exe`, no Python or installer required. All data (models, config, logs) stored relative to the app directory
- **Auto-updater**: Checks GitHub Releases 8 seconds after launch. Shows an interactive toast with Yes/No (auto-dismisses after 10s). On accept, downloads the update, writes a batch script that restarts the app with the new version. Also adds a "Check for Updates" button and version display in Settings
- **Download auto-recovery**: Detects and cleans up partially downloaded models (`.incomplete` blobs or missing `model.bin`) on startup and before retries, so interrupted downloads no longer cause cryptic errors
- **PyInstaller build spec**: `resonance.spec` bundles faster-whisper, CTranslate2 native DLLs, icons, and package metadata for `importlib.metadata.version()` support
- **packaging dependency**: Added `packaging>=23.0` for semantic version comparison in the updater

### v3.0.1
- **Self-learning pipeline wiring**: Learned vocabulary from past sessions is now merged with OCR proper nouns and fed to Whisper as vocabulary hints. Style adaptation hints are appended to the post-processing system prompt. Previously, self-learning only observed and recorded data — now it actively improves transcription accuracy
- **Feature Layers documentation**: Added a detailed section to README showing concrete before/after examples for each feature level (Whisper only → Post-Processing → OSR → Self-Learning)

### v3.0.0
- **On-Screen Recognition (OSR)**: OCR captures the active window during recording to extract proper nouns as Whisper vocabulary hints and detect app type (chat, email, code, terminal, document) for format-specific post-processing prompts
- **Self-learning recognition**: Passively builds per-app profiles over time — learns vocabulary, communication style (message length, capitalization, punctuation, formality), and app types with increasing confidence. Profiles persist across sessions in a separate JSON store
- **App detection badges**: During typing, shows detected app context above the transcription pill — generic type ("Chat", "Email") with OSR only, specific app name ("Discord", "Outlook") with self-learning enabled. Hidden for general/unknown apps
- **Estimated accuracy badge**: Displays Whisper's confidence score (derived from avg_logprob) on every transcription
- **Terminal app type**: Discriminates terminals from code editors with dedicated formatting prompt
- **WASAPI audio filtering**: Microphone dropdown shows only WASAPI devices, eliminating duplicate entries from MME/DirectSound/WDM-KS
- **Dependency-chained settings**: Post-Processing → OSR → Self-Learning toggles with grayed-out labels showing requirements
- **Learning statistics**: Four stat cards in settings — Apps Learned, Words Learned, Top App, Avg Confidence
- **Comma-spam guard**: Post-processor rejects output with excessive comma insertion
- **Larger typing indicator**: "Text Entered" and "Typing" pill enlarged with bigger text for better visibility

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
