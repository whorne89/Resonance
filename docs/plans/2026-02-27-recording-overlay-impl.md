# Recording Overlay Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a floating pill-shaped overlay with live waveform and sound effects to replace tray-only state feedback, plus extract dictionary logic from main.py.

**Architecture:** Frameless QPainter-rendered QWidget overlay positioned at bottom-center of screen. Programmatic sine-wave tones via numpy+sounddevice. Dictionary processing extracted to `core/dictionary.py`. AudioRecorder modified to expose real-time RMS levels.

**Tech Stack:** PySide6 (QPainter, QPropertyAnimation, QTimer), numpy, sounddevice — all existing dependencies.

---

### Task 1: Expose real-time audio levels from AudioRecorder

The overlay needs live audio levels. Rather than peeking into the audio queue (which risks data loss), add a `current_rms` attribute updated in the recording callback.

**Files:**
- Modify: `src/core/audio_recorder.py:14-31` (init), `src/core/audio_recorder.py:63-68` (callback)

**Step 1: Add `current_rms` attribute to AudioRecorder.__init__**

In `src/core/audio_recorder.py`, add one line after `self.logger = get_logger()` (line 31):

```python
self.current_rms = 0.0  # Real-time audio level for overlay visualization
```

**Step 2: Compute RMS in the audio callback**

In `src/core/audio_recorder.py`, inside the `callback` function (line 63-68), replace:

```python
def callback(indata, frames, time, status):
    """Callback for sounddevice to handle incoming audio data."""
    if status:
        self.logger.warning(f"Audio recording status: {status}")
    if self.recording:
        self.audio_queue.put(indata.copy())
```

with:

```python
def callback(indata, frames, time, status):
    """Callback for sounddevice to handle incoming audio data."""
    if status:
        self.logger.warning(f"Audio recording status: {status}")
    if self.recording:
        self.audio_queue.put(indata.copy())
        self.current_rms = float(np.sqrt(np.mean(indata ** 2)))
```

**Step 3: Reset RMS when recording stops**

In `src/core/audio_recorder.py`, inside `stop_recording()`, add after `self.recording = False` (line 94):

```python
self.current_rms = 0.0
```

**Step 4: Test manually**

Run: `cd src && python -c "from core.audio_recorder import AudioRecorder; r = AudioRecorder(); print(r.current_rms)"`
Expected: `0.0`

**Step 5: Commit**

```bash
git add src/core/audio_recorder.py
git commit -m "feat: expose real-time RMS audio level from AudioRecorder"
```

---

### Task 2: Extract dictionary logic to core/dictionary.py

Move `apply_dictionary()` (lines 221-256) and `_apply_fuzzy_dictionary()` (lines 258-342) from `src/main.py` into a new `DictionaryProcessor` class.

**Files:**
- Create: `src/core/dictionary.py`
- Modify: `src/main.py:1-11` (imports), `src/main.py:64-99` (init), `src/main.py:221-342` (remove methods), `src/main.py:344-359` (update caller)

**Step 1: Create `src/core/dictionary.py`**

```python
"""
Dictionary-based post-transcription word replacement.
Applies exact and fuzzy matching to fix common Whisper misrecognitions.
"""

import re
from difflib import SequenceMatcher


class DictionaryProcessor:
    """Applies custom dictionary replacements to transcribed text."""

    def __init__(self, config, logger):
        """
        Initialize dictionary processor.

        Args:
            config: ConfigManager instance
            logger: Logger instance
        """
        self.config = config
        self.logger = logger

    def apply(self, text):
        """
        Apply custom dictionary replacements to transcribed text.

        Two-phase approach:
        1. Exact matching — replaces known wrong variations case-insensitively
        2. Fuzzy matching — catches unknown variations by comparing
           sliding n-gram windows against dictionary words using
           normalized character similarity

        Args:
            text: Raw transcribed text

        Returns:
            Text with dictionary replacements applied
        """
        if not self.config.get_dictionary_enabled():
            return text

        replacements = self.config.get_dictionary_replacements()
        if not replacements:
            return text

        # Phase 1: Exact matching (known variations)
        for correct_word, wrong_variations in replacements.items():
            if not isinstance(wrong_variations, list):
                continue
            for wrong in wrong_variations:
                pattern = re.compile(re.escape(wrong), re.IGNORECASE)
                text = pattern.sub(correct_word, text)

        # Phase 2: Fuzzy matching (unknown variations)
        if self.config.get_dictionary_fuzzy_enabled():
            text = self._apply_fuzzy(text, replacements)

        return text

    def _apply_fuzzy(self, text, replacements):
        """
        Fuzzy matching pass for dictionary replacements.

        Scans the transcription using sliding windows of 1-4 words.
        For each window, normalizes both the window text and the
        dictionary word (lowercase, strip spaces/punctuation), then
        compares similarity. If a window is close enough to a
        dictionary word, it gets replaced.
        """
        threshold = self.config.get_dictionary_fuzzy_threshold()
        words = text.split()

        if not words:
            return text

        # Build targets: (correct_word, normalized_form)
        targets = []
        for correct_word in replacements:
            norm = re.sub(r'[^a-z0-9]', '', correct_word.lower())
            if len(norm) >= 3:  # Skip very short words to avoid false positives
                targets.append((correct_word, norm))

        if not targets:
            return text

        result = []
        i = 0

        while i < len(words):
            best_match = None
            best_ratio = threshold
            best_window = 0

            for correct_word, norm_correct in targets:
                # Skip if this word was already the correct word (from phase 1)
                if i < len(words) and words[i].lower() == correct_word.lower():
                    continue

                # Max window size based on correct word length
                # "Kubernetes" (10 chars) -> up to 4 words ("Cooper Netties")
                max_win = min(4, max(2, len(norm_correct) // 3 + 1))

                for ws in range(1, min(max_win + 1, len(words) - i + 1)):
                    window_text = ' '.join(words[i:i + ws])
                    norm_window = re.sub(r'[^a-z0-9]', '', window_text.lower())

                    if not norm_window:
                        continue

                    # Length ratio check
                    len_ratio = min(len(norm_correct), len(norm_window)) / max(len(norm_correct), len(norm_window))
                    if len_ratio < 0.6:
                        continue

                    ratio = SequenceMatcher(None, norm_correct, norm_window).ratio()
                    if ratio > best_ratio:
                        best_match = correct_word
                        best_ratio = ratio
                        best_window = ws

            if best_match and best_window > 0:
                # Preserve trailing punctuation from the last word in the window
                last_word = words[i + best_window - 1]
                trailing = ''
                stripped = last_word
                while stripped and not stripped[-1].isalnum():
                    trailing = stripped[-1] + trailing
                    stripped = stripped[:-1]

                result.append(best_match + trailing)
                self.logger.info(
                    f"Fuzzy match: '{' '.join(words[i:i + best_window])}' -> "
                    f"'{best_match}' (similarity: {best_ratio:.2f})"
                )
                i += best_window
            else:
                result.append(words[i])
                i += 1

        return ' '.join(result)
```

**Step 2: Update `src/main.py` — add import, remove old code, wire new class**

In `src/main.py`, add import after line 26 (`from core.hotkey_manager import HotkeyManager`):

```python
from core.dictionary import DictionaryProcessor
```

Remove imports that are no longer needed in main.py (line 2 and line 9):
- Remove `import re`
- Remove `from difflib import SequenceMatcher`

In `VTTApplication.__init__()`, add after `self.hotkey_manager = HotkeyManager()` (line 81):

```python
self.dictionary = DictionaryProcessor(self.config, self.logger)
```

Delete the `apply_dictionary()` method (lines 221-256) and `_apply_fuzzy_dictionary()` method (lines 258-342) entirely from VTTApplication.

In `on_transcription_complete()`, replace `text = self.apply_dictionary(text)` with:

```python
text = self.dictionary.apply(text)
```

**Step 3: Verify the app still runs**

Run: `cd src && python main.py`
Expected: App starts, tray icon appears. Record and transcribe to verify dictionary still works.

**Step 4: Commit**

```bash
git add src/core/dictionary.py src/main.py
git commit -m "refactor: extract dictionary processing to core/dictionary.py"
```

---

### Task 3: Create sound effects module

**Files:**
- Create: `src/core/sound_effects.py`

**Step 1: Create `src/core/sound_effects.py`**

```python
"""
Sound effects for Resonance.
Generates short tones programmatically using numpy + sounddevice.
"""

import numpy as np
import sounddevice as sd
import threading

from utils.logger import get_logger


class SoundEffects:
    """Generates and plays short notification tones."""

    def __init__(self, sample_rate=44100, volume=0.15):
        """
        Initialize sound effects.

        Args:
            sample_rate: Audio sample rate for tone generation
            volume: Volume level (0.0 to 1.0)
        """
        self.sample_rate = sample_rate
        self.volume = volume
        self.logger = get_logger()

        # Pre-generate tones at init so playback is instant
        self._start_tone = self._generate_sweep(
            freq_start=880, freq_end=1100, duration=0.15
        )
        self._stop_tone = self._generate_sweep(
            freq_start=1100, freq_end=880, duration=0.15
        )

    def _generate_sweep(self, freq_start, freq_end, duration):
        """
        Generate a frequency sweep (ascending or descending tone).

        Args:
            freq_start: Starting frequency in Hz
            freq_end: Ending frequency in Hz
            duration: Duration in seconds

        Returns:
            numpy array of audio samples
        """
        t = np.linspace(0, duration, int(self.sample_rate * duration), endpoint=False)

        # Linear frequency sweep
        freq = np.linspace(freq_start, freq_end, len(t))
        phase = 2 * np.pi * np.cumsum(freq) / self.sample_rate

        # Sine wave with envelope (fade in/out to avoid clicks)
        tone = np.sin(phase) * self.volume

        # Apply smooth envelope (raised cosine fade in/out)
        fade_samples = int(self.sample_rate * 0.02)  # 20ms fade
        if fade_samples > 0 and len(tone) > 2 * fade_samples:
            fade_in = 0.5 * (1 - np.cos(np.linspace(0, np.pi, fade_samples)))
            fade_out = 0.5 * (1 + np.cos(np.linspace(0, np.pi, fade_samples)))
            tone[:fade_samples] *= fade_in
            tone[-fade_samples:] *= fade_out

        return tone.astype(np.float32)

    def play_start_tone(self):
        """Play ascending tone (recording started). Non-blocking."""
        self._play_async(self._start_tone)

    def play_stop_tone(self):
        """Play descending tone (recording stopped). Non-blocking."""
        self._play_async(self._stop_tone)

    def _play_async(self, tone):
        """Play a tone in a background thread to avoid blocking."""
        def _play():
            try:
                sd.play(tone, samplerate=self.sample_rate, blocking=True)
            except Exception as e:
                self.logger.warning(f"Sound playback failed: {e}")

        thread = threading.Thread(target=_play, daemon=True)
        thread.start()
```

**Step 2: Test tone generation**

Run: `cd src && python -c "from core.sound_effects import SoundEffects; s = SoundEffects(); s.play_start_tone(); import time; time.sleep(0.5); s.play_stop_tone(); time.sleep(0.5)"`
Expected: Hear two short tones — ascending then descending.

**Step 3: Commit**

```bash
git add src/core/sound_effects.py
git commit -m "feat: add programmatic sound effects for recording start/stop"
```

---

### Task 4: Create recording overlay widget

**Files:**
- Create: `src/gui/recording_overlay.py`

**Step 1: Create `src/gui/recording_overlay.py`**

```python
"""
Recording overlay for Resonance.
Floating pill-shaped widget showing recording/processing state with live waveform.
"""

import numpy as np
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, Property
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QPainterPath, QGuiApplication


class RecordingOverlay(QWidget):
    """
    Frameless, transparent, always-on-top pill overlay.

    States:
    - Hidden: not visible
    - Recording: red dot (pulsing) + live waveform bars
    - Processing: blue animated dots
    """

    # Constants
    PILL_WIDTH = 200
    PILL_HEIGHT = 44
    PILL_RADIUS = 22
    BOTTOM_MARGIN = 60
    BAR_COUNT = 7
    WAVEFORM_UPDATE_MS = 50
    DOT_PULSE_MS = 40

    # Colors
    BG_COLOR = QColor(26, 26, 46, 217)       # #1a1a2e at ~85% opacity
    BORDER_COLOR = QColor(45, 45, 78, 128)    # #2d2d4e at 50%
    REC_COLOR = QColor(231, 76, 60)           # #e74c3c red
    PROC_COLOR = QColor(52, 152, 219)         # #3498db blue

    def __init__(self, parent=None):
        super().__init__(parent)

        # State
        self._state = "hidden"  # "hidden", "recording", "processing"
        self._bar_heights = [0.0] * self.BAR_COUNT
        self._target_heights = [0.0] * self.BAR_COUNT
        self._dot_opacity = 1.0
        self._dot_direction = -1  # -1 = dimming, +1 = brightening
        self._proc_dot_index = 0
        self._proc_tick = 0

        # Audio source (set by caller)
        self._audio_recorder = None

        # Window setup
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFixedSize(self.PILL_WIDTH, self.PILL_HEIGHT)

        # Position at bottom center of primary screen
        self._position_on_screen()

        # Animation timer (drives waveform + dot pulse)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

        # Fade animation
        self._fade_anim = None

    def set_audio_recorder(self, recorder):
        """Set the audio recorder to read RMS levels from."""
        self._audio_recorder = recorder

    def _position_on_screen(self):
        """Position the overlay at bottom-center of the primary screen."""
        screen = QGuiApplication.primaryScreen()
        if screen:
            geom = screen.availableGeometry()
            x = geom.x() + (geom.width() - self.PILL_WIDTH) // 2
            y = geom.y() + geom.height() - self.PILL_HEIGHT - self.BOTTOM_MARGIN
            self.move(x, y)

    # --- Public API ---

    def show_recording(self):
        """Show overlay in recording state."""
        self._state = "recording"
        self._bar_heights = [0.0] * self.BAR_COUNT
        self._target_heights = [0.0] * self.BAR_COUNT
        self._dot_opacity = 1.0
        self._dot_direction = -1
        self._stop_fade()
        self.setWindowOpacity(1.0)
        self.show()
        self.raise_()
        self._timer.start(self.WAVEFORM_UPDATE_MS)

    def show_processing(self):
        """Transition to processing state."""
        self._state = "processing"
        self._bar_heights = [0.0] * self.BAR_COUNT
        self._proc_dot_index = 0
        self._proc_tick = 0
        self.update()

    def hide_overlay(self):
        """Fade out and hide the overlay."""
        self._timer.stop()
        self._state = "hidden"
        self._fade_out()

    # --- Animation ---

    def _tick(self):
        """Called every WAVEFORM_UPDATE_MS to update animations."""
        if self._state == "recording":
            self._update_waveform()
            self._update_dot_pulse()
        elif self._state == "processing":
            self._proc_tick += 1
            if self._proc_tick % 4 == 0:  # Every ~200ms
                self._proc_dot_index = (self._proc_dot_index + 1) % 3
        self.update()

    def _update_waveform(self):
        """Update waveform bar heights from live audio RMS."""
        rms = 0.0
        if self._audio_recorder is not None:
            rms = self._audio_recorder.current_rms

        # Scale RMS to 0-1 range (calibrated for speech)
        level = min(1.0, rms * 8.0)

        # Shift bars left, add new level on the right
        self._target_heights = self._target_heights[1:] + [level]

        # Smooth interpolation toward targets
        for i in range(self.BAR_COUNT):
            diff = self._target_heights[i] - self._bar_heights[i]
            self._bar_heights[i] += diff * 0.4

    def _update_dot_pulse(self):
        """Pulse the recording dot opacity."""
        self._dot_opacity += self._dot_direction * 0.04
        if self._dot_opacity <= 0.4:
            self._dot_opacity = 0.4
            self._dot_direction = 1
        elif self._dot_opacity >= 1.0:
            self._dot_opacity = 1.0
            self._dot_direction = -1

    def _fade_out(self):
        """Animate fade out."""
        self._stop_fade()
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(300)
        self._fade_anim.setStartValue(self.windowOpacity())
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._fade_anim.finished.connect(self.hide)
        self._fade_anim.start()

    def _stop_fade(self):
        """Stop any running fade animation."""
        if self._fade_anim is not None:
            self._fade_anim.stop()
            self._fade_anim = None

    # --- Painting ---

    def paintEvent(self, event):
        """Draw the pill overlay."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw pill background
        path = QPainterPath()
        path.addRoundedRect(
            0.5, 0.5,
            self.PILL_WIDTH - 1, self.PILL_HEIGHT - 1,
            self.PILL_RADIUS, self.PILL_RADIUS
        )

        painter.setPen(QPen(self.BORDER_COLOR, 1))
        painter.setBrush(QBrush(self.BG_COLOR))
        painter.drawPath(path)

        if self._state == "recording":
            self._paint_recording(painter)
        elif self._state == "processing":
            self._paint_processing(painter)

        painter.end()

    def _paint_recording(self, painter):
        """Draw recording indicator: pulsing red dot + waveform bars."""
        # Pulsing red dot
        dot_color = QColor(self.REC_COLOR)
        dot_color.setAlphaF(self._dot_opacity)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(dot_color))
        dot_x = 24
        dot_y = self.PILL_HEIGHT // 2
        painter.drawEllipse(dot_x - 5, dot_y - 5, 10, 10)

        # Waveform bars
        bar_area_start = 50
        bar_area_width = self.PILL_WIDTH - 70
        bar_spacing = bar_area_width / self.BAR_COUNT
        bar_width = max(3, bar_spacing * 0.6)
        max_bar_height = self.PILL_HEIGHT - 16

        for i, height in enumerate(self._bar_heights):
            bar_h = max(3, height * max_bar_height)
            x = bar_area_start + i * bar_spacing + (bar_spacing - bar_width) / 2
            y = (self.PILL_HEIGHT - bar_h) / 2

            bar_color = QColor(self.REC_COLOR)
            bar_color.setAlphaF(0.6 + height * 0.4)
            painter.setBrush(QBrush(bar_color))
            painter.drawRoundedRect(int(x), int(y), int(bar_width), int(bar_h), 2, 2)

    def _paint_processing(self, painter):
        """Draw processing indicator: three animated dots."""
        painter.setPen(Qt.PenStyle.NoPen)
        center_x = self.PILL_WIDTH // 2
        center_y = self.PILL_HEIGHT // 2
        dot_spacing = 16

        for i in range(3):
            x = center_x + (i - 1) * dot_spacing
            is_active = (i == self._proc_dot_index)
            color = QColor(self.PROC_COLOR)
            color.setAlphaF(1.0 if is_active else 0.3)
            painter.setBrush(QBrush(color))
            radius = 5 if is_active else 4
            painter.drawEllipse(x - radius, center_y - radius, radius * 2, radius * 2)
```

**Step 2: Test overlay visually**

Run: `cd src && python -c "
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from gui.recording_overlay import RecordingOverlay

app = QApplication(sys.argv)
overlay = RecordingOverlay()
overlay.show_recording()
QTimer.singleShot(3000, lambda: overlay.show_processing())
QTimer.singleShot(5000, lambda: overlay.hide_overlay())
QTimer.singleShot(6000, app.quit)
app.exec()
"`
Expected: Pill appears at bottom-center with pulsing red dot and flat bars (no audio source connected). After 3s transitions to processing dots. After 5s fades out.

**Step 3: Commit**

```bash
git add src/gui/recording_overlay.py
git commit -m "feat: add recording overlay widget with waveform and processing states"
```

---

### Task 5: Wire overlay, sounds, and dictionary into main.py

Connect all new components to the application's hotkey flow.

**Files:**
- Modify: `src/main.py:1-11` (imports), `src/main.py:61-99` (init), `src/main.py:116-158` (hotkey handlers), `src/main.py:344-402` (transcription handlers), `src/main.py:482-494` (quit), `src/main.py:497-529` (main function)

**Step 1: Add imports to main.py**

At the top of `src/main.py`, the imports section (lines 1-30) should become:

```python
"""
Resonance - Voice to Text Application
Main entry point that orchestrates all components.
"""

import sys
import ctypes
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QObject, Signal, QThread, QTimer, Qt


def set_windows_app_id():
    """Set Windows AppUserModelID for proper taskbar/tray display."""
    try:
        app_id = "Resonance.VoiceToText.1.0"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass

from core.audio_recorder import AudioRecorder
from core.transcriber import Transcriber
from core.keyboard_typer import KeyboardTyper
from core.hotkey_manager import HotkeyManager
from core.dictionary import DictionaryProcessor
from core.sound_effects import SoundEffects
from gui.system_tray import SystemTrayIcon
from gui.recording_overlay import RecordingOverlay
from gui.settings_dialog import SettingsDialog
from utils.config import ConfigManager
from utils.logger import setup_logger
```

Note: `import re` and `from difflib import SequenceMatcher` are removed (they moved to `core/dictionary.py`).

**Step 2: Initialize new components in VTTApplication.__init__**

In `VTTApplication.__init__()`, add after `self.hotkey_manager = HotkeyManager()` (line 81):

```python
self.dictionary = DictionaryProcessor(self.config, self.logger)
self.sound_effects = SoundEffects()
```

Add after `self.settings_dialog = None` (line 90):

```python
self.overlay = None  # Created in main() after QApplication exists
```

**Step 3: Update on_hotkey_press to show overlay + play sound**

Replace the `on_hotkey_press` method (lines 116-129) with:

```python
def on_hotkey_press(self):
    """Called when hotkey is pressed - start recording."""
    try:
        self.logger.info("Hotkey pressed - starting recording")
        self.audio_recorder.start_recording()

        # Play start tone
        self.sound_effects.play_start_tone()

        # Update UI
        if self.tray_icon:
            self.tray_icon.set_recording_state()
        if self.overlay:
            self.overlay.show_recording()

    except Exception as e:
        self.logger.error(f"Failed to start recording: {e}")
        if self.tray_icon:
            self.tray_icon.show_error(f"Recording failed: {e}")
```

**Step 4: Update on_hotkey_release to transition overlay + play sound**

Replace the `on_hotkey_release` method (lines 131-158) with:

```python
def on_hotkey_release(self):
    """Called when hotkey is released - stop recording and transcribe."""
    try:
        self.logger.info("Hotkey released - stopping recording")

        # Stop recording and get audio data
        audio_data = self.audio_recorder.stop_recording()

        # Play stop tone
        self.sound_effects.play_stop_tone()

        if audio_data is None or len(audio_data) == 0:
            self.logger.warning("No audio data recorded")
            if self.tray_icon:
                self.tray_icon.set_idle_state()
            if self.overlay:
                self.overlay.hide_overlay()
            return

        self.logger.info(f"Audio recorded: {len(audio_data)} samples")

        # Update UI to transcribing state
        if self.tray_icon:
            self.tray_icon.set_transcribing_state()
        if self.overlay:
            self.overlay.show_processing()

        # Run transcription in background thread
        self.start_transcription(audio_data)

    except Exception as e:
        self.logger.error(f"Failed to process recording: {e}")
        if self.tray_icon:
            self.tray_icon.show_error(f"Processing failed: {e}")
            self.tray_icon.set_idle_state()
        if self.overlay:
            self.overlay.hide_overlay()
```

**Step 5: Update on_transcription_complete to hide overlay and use DictionaryProcessor**

In `on_transcription_complete` (lines 344-385), make two changes:

1. Replace `text = self.apply_dictionary(text)` with `text = self.dictionary.apply(text)`

2. Add overlay hide before `if self.tray_icon: self.tray_icon.set_idle_state()`:

```python
if self.overlay:
    self.overlay.hide_overlay()
```

**Step 6: Update on_transcription_error to hide overlay**

In `on_transcription_error` (lines 387-402), add before `if self.tray_icon:`:

```python
if self.overlay:
    self.overlay.hide_overlay()
```

**Step 7: Create overlay in main() function**

In the `main()` function (lines 497-529), add after `vtt_app = VTTApplication()` (line 508):

```python
# Create recording overlay
overlay = RecordingOverlay()
overlay.set_audio_recorder(vtt_app.audio_recorder)
vtt_app.overlay = overlay
```

**Step 8: Delete the old apply_dictionary and _apply_fuzzy_dictionary methods**

Remove the entire `apply_dictionary` method (lines 221-256) and `_apply_fuzzy_dictionary` method (lines 258-342) from VTTApplication. These now live in `core/dictionary.py`.

**Step 9: Test the full flow**

Run: `cd src && python main.py`

1. App starts, tray icon appears
2. Hold hotkey -> hear ascending tone, pill appears at bottom-center with pulsing red dot + waveform bars responding to voice
3. Release hotkey -> hear descending tone, pill transitions to processing dots
4. Transcription completes -> pill fades out, text typed into active window
5. Dictionary replacements still work

**Step 10: Commit**

```bash
git add src/main.py
git commit -m "feat: wire recording overlay, sound effects, and dictionary processor into app"
```

---

### Task 6: Clean up deleted post_processor.py

The file `src/core/post_processor.py` still exists on disk from the reverted post-processing feature but is not used. Remove it.

**Step 1: Delete the file**

```bash
rm src/core/post_processor.py
```

**Step 2: Verify no imports reference it**

Run: `grep -r "post_processor" src/`
Expected: No results

**Step 3: Commit**

```bash
git add -A src/core/post_processor.py
git commit -m "chore: remove unused post_processor.py"
```
