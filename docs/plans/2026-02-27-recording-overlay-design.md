# Recording Overlay & Code Cleanup Design

**Goal:** Add a floating pill-shaped overlay that shows recording/processing state with live waveform and sound effects, plus extract dictionary logic from main.py.

**Architecture:** Frameless QWidget overlay with QPainter rendering, positioned at bottom-center of primary screen. Programmatic sound generation via numpy + sounddevice. Dictionary processing extracted to its own core module.

**Tech Stack:** PySide6 (QPainter, QPropertyAnimation), numpy, sounddevice (all existing dependencies)

---

## 1. Recording Overlay (`src/gui/recording_overlay.py`)

### Widget: `RecordingOverlay(QWidget)`

Frameless, transparent, always-on-top pill widget with three states:

**Recording state:**
- Dark semi-transparent pill (#1a1a2e, ~85% opacity)
- Small red dot (left side, pulsing)
- Live waveform bars (5-7 vertical bars, heights driven by real mic RMS)
- No text label — visuals only

**Processing state:**
- Same pill shape
- Red dot replaced with blue/white spinner or animated dots
- Waveform replaced with processing indicator

**Hidden state:**
- Fades out via QPropertyAnimation on windowOpacity (~300ms)
- Widget hidden after fade completes

### Technical Details

- **Window flags:** `FramelessWindowHint | WindowStaysOnTopHint | Tool | WindowTransparentForInput`
  - `Tool` prevents taskbar entry
  - `WindowTransparentForInput` makes overlay click-through (never steals focus)
- **Position:** Bottom-center of primary screen, ~60px from bottom edge
- **Size:** ~280x48px pill with rounded corners (24px radius)
- **Waveform update:** QTimer at ~60ms reads audio chunks from `AudioRecorder.audio_queue`, computes per-chunk RMS, updates bar heights with smoothing/interpolation
- **Fade animations:** QPropertyAnimation on `windowOpacity` — 150ms fade-in, 300ms fade-out

### Color Palette

| Element | Color |
|---------|-------|
| Pill background | #1a1a2e at 85% opacity |
| Recording dot | #e74c3c (red), pulsing between 60-100% opacity |
| Waveform bars | #e74c3c (red) with slight gradient |
| Processing indicator | #3498db (blue) |
| Pill border | #2d2d4e at 50% opacity |

### State Machine

```
Hidden --[hotkey press]--> Recording (fade in + start sound)
Recording --[hotkey release]--> Processing (transition animation)
Processing --[transcription complete]--> Hidden (fade out + stop sound)
Processing --[transcription error]--> Hidden (fade out)
```

## 2. Sound Effects (`src/core/sound_effects.py`)

### Module: `SoundEffects`

Generates short sine-wave tones programmatically. No WAV files needed.

- **Recording start:** Soft ascending tone, ~200ms, 880Hz rising to 1100Hz, ~30% amplitude
- **Recording stop/processing start:** Soft descending tone, ~200ms, 1100Hz falling to 880Hz, ~30% amplitude
- **Playback:** Non-blocking via sounddevice (plays in background, doesn't delay recording)

### API

```python
class SoundEffects:
    def play_start_tone(self) -> None
    def play_stop_tone(self) -> None
```

Sample rate matches existing audio config (16kHz or device default).

## 3. Dictionary Extraction (`src/core/dictionary.py`)

### Class: `DictionaryProcessor`

Extract `apply_dictionary()` and `_apply_fuzzy_dictionary()` from `VTTApplication` in main.py.

```python
class DictionaryProcessor:
    def __init__(self, config: ConfigManager, logger):
        self.config = config
        self.logger = logger

    def apply(self, text: str) -> str:
        """Apply exact + fuzzy dictionary replacements."""
        ...
```

Moves ~120 lines of text processing out of main.py. The `VTTApplication` calls `self.dictionary.apply(text)` instead of `self.apply_dictionary(text)`.

## 4. Integration Changes

### `src/main.py` modifications:

- Import `RecordingOverlay`, `SoundEffects`, `DictionaryProcessor`
- Create overlay and sound_effects in `VTTApplication.__init__()`
- `on_hotkey_press()`: Show overlay (recording state) + play start tone
- `on_hotkey_release()`: Transition overlay to processing state + play stop tone
- `on_transcription_complete()`: Hide overlay (fade out)
- `on_transcription_error()`: Hide overlay (fade out)
- Replace `self.apply_dictionary(text)` with `self.dictionary.apply(text)`
- Remove `apply_dictionary()` and `_apply_fuzzy_dictionary()` methods

### `src/gui/system_tray.py` modifications:

- Keep tray icon state changes (idle/recording icons still useful as secondary indicator)
- Remove tray notification popups for transcription complete (overlay replaces this)
- Keep error notifications in tray (they show different info than overlay)

## 5. File Changes Summary

| Action | File | Lines |
|--------|------|-------|
| Create | `src/gui/recording_overlay.py` | ~200 |
| Create | `src/core/sound_effects.py` | ~60 |
| Create | `src/core/dictionary.py` | ~130 |
| Modify | `src/main.py` | ~-120 (extract), ~+30 (wire) |
| Modify | `src/gui/system_tray.py` | ~-10 (remove notification) |

**No new dependencies.** All features built on existing PySide6, numpy, sounddevice.
