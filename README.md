# Resonance

A local voice-to-text dictation application for Windows using OpenAI Whisper. Type with your voice in any application - browsers, chat windows, code editors, and more.

## Features

- **Push-to-talk recording**: Press and hold a hotkey to record, release to transcribe
- **System-wide input**: Works in any application (browsers, editors, chat apps, Claude, etc.)
- **Local processing**: Uses Whisper AI running locally on your computer (no cloud, no API costs)
- **Fast transcription**: Uses faster-whisper (4x faster than standard Whisper)
- **Simple interface**: Minimal system tray application
- **Configurable**: Customize hotkey, model size, and audio device

## Requirements

- **Windows 10/11**, **Linux**, or **macOS**
- Python 3.9 or higher
- Microphone
- **Platform-specific audio libraries**:
  - **Linux**: `libportaudio2` and `portaudio19-dev`
  - **macOS**: PortAudio (installed via Homebrew)
  - **Windows**: No additional setup needed

## Installation

### Option 1: Run from Source (Recommended)

1. Clone or download this repository
2. **Install uv** (if not already installed):
   - **Windows (PowerShell):**
     ```powershell
     powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
     ```
   - **Linux / macOS:**
     ```bash
     curl -LsSf https://astral.sh/uv/install.sh | sh
     ```
   - **Alternative (any OS):**
     ```bash
     pip install uv
     ```
3. **Install system audio libraries** (Linux/macOS only):
   - **Linux**: `sudo apt-get install libportaudio2 portaudio19-dev`
   - **macOS**: `brew install portaudio`
   - **Windows**: No additional setup needed
4. **Run the application:**
   - **Windows**: Double-click `START RESONANCE.bat`
   - **Linux / macOS**: `uv run python src/main.py`

### Option 2: Build Executable (Windows)

1. Clone or download this repository
2. Install `uv` (see step 2 above)
3. Double-click `BUILD RESONANCE.bat`
4. The executable will be created at `dist\Resonance\Resonance.exe`
5. Copy the entire `dist\Resonance` folder anywhere - no installation needed!

## Usage

1. Launch the application (system tray icon will appear)
2. Open any application where you want to type
3. **Press and hold `Ctrl+Alt+R`** (default hotkey)
4. Speak into your microphone
5. **Release the hotkey** to transcribe
6. Text will be automatically typed into the active window

## Configuration

Right-click the system tray icon and select **Settings** to configure:

- **Hotkey**: Change the push-to-talk keyboard shortcut
- **Model Size**: Choose between tiny, base, small, medium, or large Whisper models
  - **tiny**: Fastest, lower accuracy (~70MB)
  - **base**: Fast, decent accuracy (~140MB)
  - **small**: Balanced (default) (~500MB)
  - **medium**: Better accuracy, slower (~1.5GB)
  - **large**: Best accuracy, slowest (~3GB)
- **Audio Device**: Select which microphone to use

## Technical Details

### Technology Stack

- **PySide6**: GUI framework (system tray)
- **sounddevice**: Audio recording
- **faster-whisper**: Speech recognition (4x faster than openai-whisper)
- **pynput**: Global hotkeys and keyboard simulation

### How It Works

1. Global hotkey listener detects when you press/release the configured hotkey
2. Audio is recorded from your microphone at 16kHz (Whisper's native sample rate)
3. When you release the hotkey, the audio is sent to faster-whisper for transcription
4. Transcribed text is typed into the currently focused window using keyboard simulation

## Troubleshooting

### Windows: "uv is not recognized" error

Make sure `uv` is installed (see Installation step 2) and restart your terminal/command prompt after installation to refresh your PATH.

### OneDrive/Cloud Sync Error (Windows)

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
- Try the clipboard fallback option in Settings (if available)

### First run is slow

- The Whisper model needs to be downloaded on first use (~500MB for small model)
- Models are cached locally, subsequent runs will be faster

## License

MIT License

## Credits

Built with:

- [OpenAI Whisper](https://github.com/openai/whisper)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- [PySide6](https://www.qt.io/qt-for-python)
