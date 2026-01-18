# Changelog

All notable changes to Resonance will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.1.0] - 2026-01-18

### Added
- **Typing Method Settings**: Users can now choose between character-by-character typing or clipboard paste (Ctrl+V) in Settings
  - Clipboard paste is faster and more reliable (recommended)
  - Setting is saved and persists between sessions
- **About Dialog Window**: About now shows in a proper dialog window instead of system tray notification
- **Model Download Detection**: App now detects if a Whisper model is already downloaded before prompting
  - Shows confirmation dialog with model size before downloading
  - No restart required after changing models
- **Hotkey Capture Dialog**: New popup dialog for capturing any key combination
  - Supports modifier-only combinations (e.g., Ctrl+Alt)
  - Visual feedback while capturing keys
  - Press any combination and release to save

### Changed
- Renamed application from "Will's VTT" to "Resonance"
- Startup notification now says "Resonance Service Started"
- Hotkey display now uses proper capitalization (e.g., "Ctrl+Alt+R" instead of "ctrl+alt+r")
- Settings dialog no longer closes automatically after saving
- Removed unnecessary restart requirements
- Model downloads automatically on first use (no manual download needed)

### Fixed
- **PyInstaller Build**: Fixed executable build to properly include all modules
  - Added correct pathex and hiddenimports to build_exe.spec
  - Executable now runs without errors
- **Model Download Path**: Models now download to correct location (F:\vtt\src\models instead of C drive)
- **Microphone Test Sensitivity**: Adjusted sensitivity multiplier from 300 to 3500 for accurate level display
- **Settings Save Error**: Fixed ConfigManager.set() missing value= keyword argument
- **Transcription State Reset**: Fixed bug where transcription state wasn't properly reset

### Removed
- Transcription complete notifications (disabled by default)
- Unnecessary documentation files (old READMEs, troubleshooting guides)
- Empty tests directory
- Hotkey validation requiring modifiers (now accepts any key combination)

## [1.0.0] - 2026-01-18

### Added
- Initial release of Resonance
- Push-to-talk voice-to-text transcription using OpenAI Whisper
- System tray application with minimal UI
- Configurable hotkey (default: Ctrl+Alt+R)
- Multiple Whisper model sizes (tiny, base, small, medium, large)
- Audio device selection and microphone testing
- Local processing (no internet required)
- Works in any Windows application
- Standalone executable build support

[Unreleased]: https://github.com/whorne89/Resonance/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/whorne89/Resonance/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/whorne89/Resonance/releases/tag/v1.0.0
