"""
Settings dialog for Resonance.
Allows configuration of hotkey, model, audio device, etc.
"""

import os
import time

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QGroupBox, QLineEdit,
    QMessageBox, QFormLayout, QProgressBar, QRadioButton,
    QButtonGroup, QGridLayout, QFrame, QCheckBox
)
from PySide6.QtCore import Signal, QTimer, Qt, QThread, QObject
from PySide6.QtGui import QPalette, QColor, QKeyEvent

from gui.dictionary_dialog import DictionaryDialog
from gui.theme import RoundedDialog, MessageBox
from utils.config import format_hotkey_display


class HotkeyCaptureDialog(RoundedDialog):
    """Dialog for capturing hotkey combinations."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.captured_hotkey = None
        self.pressed_modifiers = set()
        self.pressed_key = None

        self.setWindowTitle("Capture Hotkey")
        self.setModal(True)
        self.setMinimumWidth(400)
        self.setMinimumHeight(200)

        layout = QVBoxLayout()

        # Instruction label
        self.instruction_label = QLabel("Press any key combination...")
        self.instruction_label.setStyleSheet("font-size: 14px; font-weight: bold; padding: 20px;")
        self.instruction_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.instruction_label)

        # Display label for showing current combination
        self.display_label = QLabel("")
        self.display_label.setStyleSheet("font-size: 18px; color: #3498db; padding: 10px;")
        self.display_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.display_label)

        # Cancel button
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)

        self.setLayout(layout)

    def keyPressEvent(self, event: QKeyEvent):
        """Capture key press events."""
        key = event.key()

        # Track modifiers
        if key == Qt.Key.Key_Control:
            self.pressed_modifiers.add('ctrl')
        elif key == Qt.Key.Key_Alt:
            self.pressed_modifiers.add('alt')
        elif key == Qt.Key.Key_Shift:
            self.pressed_modifiers.add('shift')
        elif key == Qt.Key.Key_Meta:
            self.pressed_modifiers.add('win')
        else:
            # Regular key pressed
            self.pressed_key = self._key_to_string(key, event.text())

        # Update display
        self._update_display()

    def keyReleaseEvent(self, event: QKeyEvent):
        """Capture key release to finalize the combination."""
        key = event.key()

        # When ANY key is released, capture the current combination
        # Build the final hotkey string
        parts = []

        # Add modifiers in consistent order
        if 'ctrl' in self.pressed_modifiers:
            parts.append('ctrl')
        if 'alt' in self.pressed_modifiers:
            parts.append('alt')
        if 'shift' in self.pressed_modifiers:
            parts.append('shift')
        if 'win' in self.pressed_modifiers:
            parts.append('win')

        # Add the main key if one was pressed
        if self.pressed_key:
            parts.append(self.pressed_key)

        # If we have any keys in the combination, save it
        if parts:
            self.captured_hotkey = '+'.join(parts)
            self.accept()
            return

        # If nothing was captured yet, remove the released modifier from the set
        if key == Qt.Key.Key_Control:
            self.pressed_modifiers.discard('ctrl')
        elif key == Qt.Key.Key_Alt:
            self.pressed_modifiers.discard('alt')
        elif key == Qt.Key.Key_Shift:
            self.pressed_modifiers.discard('shift')
        elif key == Qt.Key.Key_Meta:
            self.pressed_modifiers.discard('win')

        self._update_display()

    def _update_display(self):
        """Update the display label with current key combination."""
        parts = []

        if 'ctrl' in self.pressed_modifiers:
            parts.append('Ctrl')
        if 'alt' in self.pressed_modifiers:
            parts.append('Alt')
        if 'shift' in self.pressed_modifiers:
            parts.append('Shift')
        if 'win' in self.pressed_modifiers:
            parts.append('Win')

        if self.pressed_key:
            parts.append(self.pressed_key.upper())

        if parts:
            self.display_label.setText('+'.join(parts))
        else:
            self.display_label.setText("")

    def _key_to_string(self, key, text):
        """Convert Qt key code to string."""
        # Handle special keys
        key_map = {
            Qt.Key.Key_Space: 'space',
            Qt.Key.Key_Return: 'enter',
            Qt.Key.Key_Enter: 'enter',
            Qt.Key.Key_Tab: 'tab',
            Qt.Key.Key_Backspace: 'backspace',
            Qt.Key.Key_Escape: 'esc',
            Qt.Key.Key_Delete: 'delete',
            Qt.Key.Key_Insert: 'insert',
            Qt.Key.Key_Home: 'home',
            Qt.Key.Key_End: 'end',
            Qt.Key.Key_PageUp: 'pageup',
            Qt.Key.Key_PageDown: 'pagedown',
            Qt.Key.Key_Up: 'up',
            Qt.Key.Key_Down: 'down',
            Qt.Key.Key_Left: 'left',
            Qt.Key.Key_Right: 'right',
        }

        if key in key_map:
            return key_map[key]

        # F1-F12 keys
        if Qt.Key.Key_F1 <= key <= Qt.Key.Key_F12:
            return f'f{key - Qt.Key.Key_F1 + 1}'

        # Use the text if available, otherwise try to convert the key code
        if text and text.isprintable():
            return text.lower()
        elif 32 <= key <= 126:
            return chr(key).lower()

        return None


class _DownloadWorker(QObject):
    """Background worker for downloading a Whisper model."""

    finished = Signal()
    error = Signal(str)

    def __init__(self, transcriber, model_size):
        super().__init__()
        self.transcriber = transcriber
        self.model_size = model_size

    def run(self):
        try:
            from huggingface_hub import snapshot_download
            repo_id = (
                self.model_size if '/' in self.model_size
                else f"Systran/faster-whisper-{self.model_size}"
            )
            snapshot_download(repo_id, cache_dir=self.transcriber.models_dir)
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))


class ModelDownloadDialog(RoundedDialog):
    """Progress dialog shown while downloading a Whisper model."""

    def __init__(self, display_name, model_size, expected_mb, transcriber, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Downloading Model")
        self.setMinimumWidth(420)
        self._success = False
        self._expected_bytes = expected_mb * 1024 * 1024

        # Path that huggingface_hub downloads into
        if '/' in model_size:
            cache_name = "models--" + model_size.replace('/', '--')
        else:
            cache_name = f"models--Systran--faster-whisper-{model_size}"
        self._cache_path = os.path.join(transcriber.models_dir, cache_name)
        self._start_time = time.time()

        layout = QVBoxLayout()
        layout.setSpacing(12)

        self._status = QLabel(f"Downloading {display_name}...")
        self._status.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._status)

        self._bar = QProgressBar()
        self._bar.setMinimum(0)
        self._bar.setMaximum(100)
        self._bar.setValue(0)
        self._bar.setTextVisible(True)
        self._bar.setFormat("%v%")
        self._bar.setMinimumHeight(28)
        layout.addWidget(self._bar)

        self._time_label = QLabel("Elapsed: 0:00")
        self._time_label.setStyleSheet("color: rgba(255, 255, 255, 140); font-size: 11px;")
        layout.addWidget(self._time_label)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

        # Background download thread
        self._thread = QThread()
        self._worker = _DownloadWorker(transcriber, model_size)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)

        # Poll directory size for progress
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(500)

        self._thread.start()

    def _tick(self):
        """Update progress bar and elapsed time."""
        # Directory size → percentage
        current = self._dir_size()
        if self._expected_bytes > 0:
            pct = min(99, int(current / self._expected_bytes * 100))
        else:
            pct = 0
        self._bar.setValue(pct)

        elapsed = time.time() - self._start_time
        m, s = divmod(int(elapsed), 60)
        self._time_label.setText(f"Elapsed: {m}:{s:02d}")

    def _dir_size(self):
        total = 0
        if os.path.exists(self._cache_path):
            for dirpath, _, filenames in os.walk(self._cache_path):
                for f in filenames:
                    try:
                        total += os.path.getsize(os.path.join(dirpath, f))
                    except OSError:
                        pass
        return total

    def _on_finished(self):
        self._timer.stop()
        self._bar.setValue(100)
        self._success = True
        self._cleanup()
        self.accept()

    def _on_error(self, msg):
        self._timer.stop()
        self._cleanup()
        MessageBox.critical(self, "Download Failed", f"Failed to download model:\n\n{msg}")
        self.reject()

    def _cleanup(self):
        if self._thread:
            self._thread.quit()
            self._thread.wait(2000)
            self._thread.deleteLater()
            self._thread = None
        if self._worker:
            self._worker.deleteLater()
            self._worker = None

    def closeEvent(self, event):
        self._cleanup()
        event.accept()

    @property
    def succeeded(self):
        return self._success


class _PPDownloadWorker(QObject):
    """Background worker for downloading post-processing model."""

    finished = Signal()
    error = Signal(str)
    progress = Signal(int, int)  # downloaded, total

    def __init__(self):
        super().__init__()

    def run(self):
        try:
            from core.post_processor import PostProcessor
            pp = PostProcessor()
            pp.download_model(progress_callback=self._on_progress)
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))

    def _on_progress(self, downloaded, total):
        self.progress.emit(downloaded, total)


class PostProcessingDownloadDialog(RoundedDialog):
    """Progress dialog shown while downloading post-processing model."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Downloading Post-Processing Model")
        self.setMinimumWidth(420)
        self._success = False

        layout = QVBoxLayout()
        layout.setSpacing(12)

        self._status = QLabel("Downloading llama-server and Qwen 2.5 model...")
        self._status.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._status)

        self._bar = QProgressBar()
        self._bar.setMinimum(0)
        self._bar.setMaximum(100)
        self._bar.setValue(0)
        self._bar.setTextVisible(True)
        self._bar.setFormat("%v%")
        self._bar.setMinimumHeight(28)
        layout.addWidget(self._bar)

        self._time_label = QLabel("Elapsed: 0:00")
        self._time_label.setStyleSheet("color: rgba(255, 255, 255, 140); font-size: 11px;")
        layout.addWidget(self._time_label)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

        self._start_time = time.time()

        # Elapsed timer
        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start(500)

        # Background download thread
        self._thread = QThread()
        self._worker = _PPDownloadWorker()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.progress.connect(self._on_progress)

        self._thread.start()

    def _tick(self):
        elapsed = time.time() - self._start_time
        m, s = divmod(int(elapsed), 60)
        self._time_label.setText(f"Elapsed: {m}:{s:02d}")

    def _on_progress(self, downloaded, total):
        if total > 0:
            pct = min(99, int(downloaded / total * 100))
            self._bar.setValue(pct)
            mb_done = downloaded / (1024 * 1024)
            mb_total = total / (1024 * 1024)
            self._status.setText(f"Downloading model... {mb_done:.0f} / {mb_total:.0f} MB")

    def _on_finished(self):
        self._tick_timer.stop()
        self._bar.setValue(100)
        self._success = True
        self._cleanup()
        self.accept()

    def _on_error(self, msg):
        self._tick_timer.stop()
        self._cleanup()
        MessageBox.critical(self, "Download Failed", f"Failed to download model:\n\n{msg}")
        self.reject()

    def _cleanup(self):
        if self._thread:
            self._thread.quit()
            self._thread.wait(2000)
            self._thread.deleteLater()
            self._thread = None
        if self._worker:
            self._worker.deleteLater()
            self._worker = None

    def closeEvent(self, event):
        self._cleanup()
        event.accept()

    @property
    def succeeded(self):
        return self._success


class SettingsDialog(RoundedDialog):
    """Settings configuration dialog."""

    # Signal emitted when settings are saved
    settings_changed = Signal()

    def __init__(self, config_manager, audio_recorder, transcriber, parent=None):
        """
        Initialize settings dialog.

        Args:
            config_manager: ConfigManager instance
            audio_recorder: AudioRecorder instance
            transcriber: Transcriber instance
            parent: Parent widget
        """
        super().__init__(parent)
        self.config = config_manager
        self.audio_recorder = audio_recorder
        self.transcriber = transcriber

        self.setWindowTitle("Resonance Settings")
        self.setMinimumWidth(500)

        self.init_ui()
        self.load_current_settings()

    def init_ui(self):
        """Initialize user interface."""
        layout = QVBoxLayout()

        # Usage statistics (dashboard cards at top)
        statistics_group = self.create_statistics_group()
        layout.addWidget(statistics_group)

        # Hotkey settings
        hotkey_group = self.create_hotkey_group()
        layout.addWidget(hotkey_group)

        # Whisper model settings
        model_group = self.create_model_group()
        layout.addWidget(model_group)

        # Audio settings
        audio_group = self.create_audio_group()
        layout.addWidget(audio_group)

        # Typing settings
        typing_group = self.create_typing_group()
        layout.addWidget(typing_group)

        # Dictionary settings
        dictionary_group = self.create_dictionary_group()
        layout.addWidget(dictionary_group)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self.save_settings)
        button_layout.addWidget(self.save_button)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)

        self.setLayout(layout)

    def create_hotkey_group(self):
        """Create hotkey configuration group."""
        group = QGroupBox("Hotkey Settings")
        layout = QFormLayout()

        # Horizontal layout for hotkey display and button
        hotkey_layout = QHBoxLayout()

        # Display current hotkey
        self.hotkey_display = QLabel("ctrl+alt+r")
        self.hotkey_display.setStyleSheet("font-size: 12px; font-weight: bold; padding: 5px; border: 1px solid #3d3d5c; border-radius: 3px; background-color: #2d2d4e; color: #ffffff;")
        self.hotkey_display.setMinimumWidth(150)
        hotkey_layout.addWidget(self.hotkey_display)

        # Button to change hotkey
        self.change_hotkey_button = QPushButton("Change Hotkey")
        self.change_hotkey_button.clicked.connect(self.capture_hotkey)
        hotkey_layout.addWidget(self.change_hotkey_button)

        hotkey_layout.addStretch()

        layout.addRow("Hotkey Combination:", hotkey_layout)

        # Help text
        help_label = QLabel(
            "Click 'Change Hotkey' and press your desired key combination."
        )
        help_label.setStyleSheet("color: rgba(255, 255, 255, 140); font-size: 11px;")
        layout.addRow("", help_label)

        group.setLayout(layout)
        return group

    def capture_hotkey(self):
        """Open dialog to capture new hotkey."""
        dialog = HotkeyCaptureDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if dialog.captured_hotkey:
                self.hotkey_display.setText(format_hotkey_display(dialog.captured_hotkey))

    def create_model_group(self):
        """Create transcription engine configuration group."""
        group = QGroupBox("Speech Recognition")
        layout = QFormLayout()
        layout.setVerticalSpacing(4)

        # Model size dropdown
        self.model_combo = QComboBox()
        models = [
            ("Fastest",   "tiny"),
            ("Balanced",  "base"),
            ("Accurate",  "small"),
            ("Precision", "medium"),
        ]
        for display_name, model_id in models:
            self.model_combo.addItem(display_name, userData=model_id)

        quality_col = QVBoxLayout()
        quality_col.setSpacing(2)
        quality_col.addWidget(self.model_combo)
        quality_desc = QLabel("Select the quality level for speech recognition.")
        quality_desc.setStyleSheet("color: rgba(255, 255, 255, 140); font-size: 11px;")
        quality_col.addWidget(quality_desc)
        layout.addRow("Quality:", quality_col)

        # Model info
        info_label = QLabel(
            "Fastest \u2014 Whisper Tiny (~70 MB), sub-second\n"
            "Balanced \u2014 Whisper Base (~140 MB), sub-second\n"
            "Accurate \u2014 Whisper Small (~500 MB), ~2s\n"
            "Precision \u2014 Whisper Medium (~1.5 GB), ~5s"
        )
        info_label.setStyleSheet("color: rgba(255, 255, 255, 140); font-size: 11px;")
        layout.addRow("", info_label)

        # Post-processing checkbox + description (same pattern as Quality)
        self.post_processing_cb = QCheckBox("Post-Processing (AI)")
        pp_desc = QLabel(
            "Fixes grammar, capitalization, punctuation, contractions,\n"
            "quotations, and sentence breaks. Removes filler words\n"
            "and stutters. Powered by Qwen 2.5 (local, offline)."
        )
        pp_desc.setStyleSheet("color: rgba(255, 255, 255, 140); font-size: 11px;")

        pp_col = QVBoxLayout()
        pp_col.setSpacing(2)
        pp_col.addWidget(self.post_processing_cb)
        pp_col.addWidget(pp_desc)
        layout.addRow("", pp_col)

        group.setLayout(layout)
        return group

    def create_audio_group(self):
        """Create audio device configuration group."""
        group = QGroupBox("Audio Settings")
        layout = QFormLayout()

        # Audio device dropdown
        self.device_combo = QComboBox()
        self.populate_audio_devices()
        layout.addRow("Microphone:", self.device_combo)

        # Test button
        self.test_button = QPushButton("Test Microphone")
        self.test_button.clicked.connect(self.test_microphone)
        layout.addRow("", self.test_button)

        group.setLayout(layout)
        return group

    def create_typing_group(self):
        """Create typing method configuration group."""
        group = QGroupBox("Entry Method")
        layout = QVBoxLayout()

        # Radio buttons with inline descriptions
        self.typing_char_radio = QRadioButton("Character-by-character")
        self.typing_paste_radio = QRadioButton("Clipboard paste")

        # Button group to make them mutually exclusive
        self.typing_method_group = QButtonGroup()
        self.typing_method_group.addButton(self.typing_char_radio, 0)
        self.typing_method_group.addButton(self.typing_paste_radio, 1)

        char_row = QHBoxLayout()
        char_row.addWidget(self.typing_char_radio)
        char_desc = QLabel("Simulates keystrokes as if you were typing")
        char_desc.setStyleSheet("color: rgba(255, 255, 255, 140); font-size: 11px;")
        char_row.addWidget(char_desc)
        char_row.addStretch()
        layout.addLayout(char_row)

        paste_row = QHBoxLayout()
        paste_row.addWidget(self.typing_paste_radio)
        paste_desc = QLabel("Inserts text instantly via the clipboard")
        paste_desc.setStyleSheet("color: rgba(255, 255, 255, 140); font-size: 11px;")
        paste_row.addWidget(paste_desc)
        paste_row.addStretch()
        layout.addLayout(paste_row)

        group.setLayout(layout)
        return group

    def create_dictionary_group(self):
        """Create custom dictionary configuration group."""
        group = QGroupBox("Custom Dictionary")
        layout = QVBoxLayout()

        info_label = QLabel(
            "Add words that Resonance commonly gets wrong to improve accuracy."
        )
        info_label.setStyleSheet("color: rgba(255, 255, 255, 140); font-size: 11px;")
        layout.addWidget(info_label)

        # Count label + button
        button_layout = QHBoxLayout()

        replacements = self.config.get_dictionary_replacements()
        total_vars = sum(len(v) for v in replacements.values() if isinstance(v, list))
        self.dict_count_label = QLabel(f"{len(replacements)} word(s), {total_vars} variation(s)")
        button_layout.addWidget(self.dict_count_label)

        button_layout.addStretch()

        self.dict_button = QPushButton("Edit Dictionary...")
        self.dict_button.clicked.connect(self.open_dictionary)
        button_layout.addWidget(self.dict_button)

        layout.addLayout(button_layout)

        group.setLayout(layout)
        return group

    def _create_stat_card(self, title, value):
        """Create a single stat card widget."""
        card = QFrame()
        card.setFrameShape(QFrame.Shape.StyledPanel)
        card.setStyleSheet(
            "QFrame { background-color: #2d2d4e; border: 1px solid #3d3d5c;"
            " border-radius: 6px; padding: 8px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(8, 6, 8, 6)
        card_layout.setSpacing(2)

        title_label = QLabel(title)
        title_label.setStyleSheet("color: rgba(255, 255, 255, 140); font-size: 11px; border: none; background: transparent;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(title_label)

        value_label = QLabel(str(value))
        value_label.setStyleSheet("font-size: 18px; font-weight: bold; border: none; background: transparent; color: #ffffff;")
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(value_label)

        return card

    def _format_duration(self, seconds):
        """Format a duration in seconds to a human-readable string."""
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            return f"{seconds / 60:.1f}m"
        else:
            return f"{seconds / 3600:.1f}h"

    def create_statistics_group(self):
        """Create usage statistics as a dashboard card grid."""
        group = QGroupBox("Usage Statistics")
        outer = QVBoxLayout()

        stats = self.config.get_statistics()

        total_words = stats.get("total_words", 0)
        total_transcriptions = stats.get("total_transcriptions", 0)
        total_characters = stats.get("total_characters", 0)
        total_seconds = stats.get("total_recording_seconds", 0.0)
        first_used = stats.get("first_used")

        avg_words = round(total_words / total_transcriptions) if total_transcriptions > 0 else 0
        time_saved_seconds = (total_words / 40.0) * 60  # typing at 40 WPM
        avg_wpm = round(total_words / (total_seconds / 60)) if total_seconds > 0 else 0

        # Avg recording time per day (since first use)
        avg_rec_per_day = 0.0
        if first_used and total_seconds > 0:
            from datetime import date
            try:
                first = date.fromisoformat(first_used)
                days = max(1, (date.today() - first).days)
                avg_rec_per_day = total_seconds / days
            except ValueError:
                pass

        # Build 2 rows × 4 columns of stat cards
        grid = QGridLayout()
        grid.setSpacing(8)

        cards = [
            ("Words Dictated",    f"{total_words:,}"),
            ("Transcriptions",    f"{total_transcriptions:,}"),
            ("Avg Words",         f"{avg_words:,}"),
            ("Avg WPM",           f"{avg_wpm:,}"),
            ("Time Saved",        self._format_duration(time_saved_seconds)),
            ("Time Recorded",     self._format_duration(total_seconds)),
            ("Avg Per Day",       self._format_duration(avg_rec_per_day)),
            ("Avg Transcription", self._format_duration(total_seconds / total_transcriptions if total_transcriptions > 0 else 0)),
        ]

        for i, (title, value) in enumerate(cards):
            row, col = divmod(i, 4)
            grid.addWidget(self._create_stat_card(title, value), row, col)

        outer.addLayout(grid)

        # Reset button — small, right-aligned
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        reset_button = QPushButton("Reset Statistics")
        reset_button.clicked.connect(self.reset_statistics)
        button_layout.addWidget(reset_button)
        outer.addLayout(button_layout)

        group.setLayout(outer)
        return group

    def reset_statistics(self):
        """Reset all usage statistics after confirmation."""
        reply = MessageBox.question(
            self,
            "Reset Statistics",
            "Are you sure you want to reset all usage statistics?\n\nThis cannot be undone.",
        )
        if reply == MessageBox.Yes:
            self.config.reset_statistics()
            MessageBox.information(self, "Statistics Reset", "Usage statistics have been reset.")

    def open_dictionary(self):
        """Open the custom dictionary editor."""
        dialog = DictionaryDialog(
            self.config, self.audio_recorder, self.transcriber, self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            replacements = self.config.get_dictionary_replacements()
            total_vars = sum(len(v) for v in replacements.values() if isinstance(v, list))
            self.dict_count_label.setText(f"{len(replacements)} word(s), {total_vars} variation(s)")

    def populate_audio_devices(self):
        """Populate audio device dropdown with available devices."""
        self.device_combo.clear()

        # Add "Default" option
        self.device_combo.addItem("System Default", None)

        # Add available input devices
        try:
            devices = self.audio_recorder.get_devices()
            for device_idx, device_name in devices:
                self.device_combo.addItem(device_name, device_idx)
        except Exception as e:
            print(f"Error getting audio devices: {e}")

    def load_current_settings(self):
        """Load current settings into UI."""
        # Hotkey
        self.hotkey_display.setText(self.config.get_hotkey_display())

        # Model size
        model_size = self.config.get_model_size()
        index = self.model_combo.findData(model_size)
        if index >= 0:
            self.model_combo.setCurrentIndex(index)

        # Audio device
        device_idx = self.config.get_audio_device()
        if device_idx is None:
            self.device_combo.setCurrentIndex(0)  # Default
        else:
            # Find device in combo box
            for i in range(self.device_combo.count()):
                if self.device_combo.itemData(i) == device_idx:
                    self.device_combo.setCurrentIndex(i)
                    break

        # Typing method
        use_clipboard = self.config.get("typing", "use_clipboard_fallback", default=False)
        if use_clipboard:
            self.typing_paste_radio.setChecked(True)
        else:
            self.typing_char_radio.setChecked(True)

        # Post-processing
        self.post_processing_cb.setChecked(self.config.get_post_processing_enabled())

    def save_settings(self):
        """Save settings and emit signal."""
        try:
            # Get values from UI
            hotkey = self.hotkey_display.text().strip().lower()
            model_size = self.model_combo.currentData()
            device_idx = self.device_combo.currentData()
            use_clipboard = self.typing_paste_radio.isChecked()
            pp_enabled = self.post_processing_cb.isChecked()

            # Validate hotkey (just check it's not empty)
            if not hotkey:
                MessageBox.warning(
                    self,
                    "Invalid Hotkey",
                    "Please set a hotkey combination using the 'Change Hotkey' button."
                )
                return

            # Detect what changed
            old_hotkey = self.config.get_hotkey()
            old_model = self.config.get_model_size()
            old_device = self.config.get_audio_device()
            old_clipboard = self.config.get("typing", "use_clipboard_fallback", default=False)
            old_pp = self.config.get_post_processing_enabled()

            changes = []
            if hotkey != old_hotkey:
                changes.append(f"Hotkey \u2192 {format_hotkey_display(hotkey)}")
            if model_size != old_model:
                changes.append(f"Model \u2192 {self.model_combo.currentText()}")
            if device_idx != old_device:
                changes.append(f"Microphone \u2192 {self.device_combo.currentText()}")
            if use_clipboard != old_clipboard:
                method = "Clipboard paste" if use_clipboard else "Character-by-character"
                changes.append(f"Entry method \u2192 {method}")
            if pp_enabled != old_pp:
                changes.append(f"Post-processing \u2192 {'On' if pp_enabled else 'Off'}")

            # Nothing changed — just close
            if not changes:
                self.accept()
                return

            # Download model if it changed and isn't cached yet
            if model_size != old_model:
                if not self.transcriber.is_model_downloaded(model_size):
                    model_info = self.transcriber.get_model_size_info(model_size)
                    display_name = self.model_combo.currentText()

                    dlg = ModelDownloadDialog(
                        display_name, model_size,
                        model_info['size_mb'], self.transcriber, self,
                    )
                    dlg.exec()

                    if not dlg.succeeded:
                        return

            # Download post-processing model if enabling for the first time
            if pp_enabled and not old_pp:
                from core.post_processor import PostProcessor
                pp = PostProcessor()
                if not pp.is_model_downloaded():
                    dlg = PostProcessingDownloadDialog(self)
                    dlg.exec()
                    if not dlg.succeeded:
                        return

            # Save to config
            self.config.set_hotkey(hotkey)
            self.config.set_model_size(model_size)
            self.config.set_audio_device(device_idx)
            self.config.set("typing", "use_clipboard_fallback", value=use_clipboard)
            self.config.set_post_processing_enabled(pp_enabled)
            self.config.save()

            # Emit signal
            self.settings_changed.emit()

            # Flash confirmation showing what changed
            summary = "\n".join(f"\u2022 {c}" for c in changes)
            MessageBox.flash(self, "Settings Saved", summary)

            self.accept()

        except Exception as e:
            MessageBox.critical(
                self,
                "Error",
                f"Failed to save settings: {e}"
            )

    def test_microphone(self):
        """Test microphone with real-time audio level meter."""
        # Get selected device
        device_idx = self.device_combo.currentData()
        self.audio_recorder.set_device(device_idx)

        # Create audio meter dialog
        meter_dialog = AudioLevelMeterDialog(self.audio_recorder, self)
        meter_dialog.exec()


class AudioLevelMeterDialog(RoundedDialog):
    """Dialog showing real-time audio level meter."""

    def __init__(self, audio_recorder, parent=None):
        super().__init__(parent)
        self.audio_recorder = audio_recorder
        self.is_recording = False
        self.current_level = 0

        self.setWindowTitle("Microphone Test")
        self.setMinimumWidth(400)
        self.setMinimumHeight(250)

        self.init_ui()
        self.start_monitoring()

    def init_ui(self):
        """Initialize user interface."""
        layout = QVBoxLayout()

        # Title
        title_label = QLabel("Microphone Level Monitor")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(title_label)

        # Instructions
        instructions = QLabel("Speak into your microphone to see the audio level.")
        instructions.setStyleSheet("color: rgba(255, 255, 255, 140); margin-bottom: 10px;")
        layout.addWidget(instructions)

        # Audio level bar
        self.level_bar = QProgressBar()
        self.level_bar.setMinimum(0)
        self.level_bar.setMaximum(100)
        self.level_bar.setValue(0)
        self.level_bar.setTextVisible(True)
        self.level_bar.setFormat("%v%")
        self.level_bar.setMinimumHeight(40)

        # Style the progress bar with green color
        self.level_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #3d3d5c;
                border-radius: 5px;
                text-align: center;
                background-color: #2d2d4e;
                color: #ffffff;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4CAF50, stop:1 #8BC34A
                );
                border-radius: 3px;
            }
        """)
        layout.addWidget(self.level_bar)

        # Status label
        self.status_label = QLabel("Microphone Quality: Testing...")
        self.status_label.setStyleSheet("font-size: 12px; margin-top: 10px;")
        layout.addWidget(self.status_label)

        # Close button
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close_and_stop)
        button_layout.addWidget(self.close_button)

        layout.addLayout(button_layout)

        self.setLayout(layout)

    def start_monitoring(self):
        """Start monitoring microphone levels."""
        try:
            self.audio_recorder.start_recording()
            self.is_recording = True

            # Update timer to check audio levels
            self.update_timer = QTimer(self)
            self.update_timer.timeout.connect(self.update_level)
            self.update_timer.start(100)  # Update every 100ms

        except Exception as e:
            self.status_label.setText(f"Error: {e}")
            self.status_label.setStyleSheet("color: red; font-size: 12px;")

    def update_level(self):
        """Update the audio level display."""
        try:
            import numpy as np

            # Get audio chunks from the queue without removing them permanently
            if not self.audio_recorder.audio_queue.empty():
                # Collect recent chunks (last few)
                recent_chunks = []
                temp_chunks = []

                # Get up to 10 recent chunks
                count = 0
                while not self.audio_recorder.audio_queue.empty() and count < 10:
                    chunk = self.audio_recorder.audio_queue.get()
                    recent_chunks.append(chunk)
                    temp_chunks.append(chunk)
                    count += 1

                # Put the last 5 chunks back in queue (keep queue from growing infinitely)
                for chunk in temp_chunks[-5:]:
                    self.audio_recorder.audio_queue.put(chunk)

                if recent_chunks:
                    # Concatenate recent chunks
                    recent_data = np.concatenate(recent_chunks, axis=0)

                    # Flatten if needed
                    if recent_data.ndim > 1:
                        recent_data = recent_data.flatten()

                    # Calculate RMS (Root Mean Square) for better level representation
                    rms = np.sqrt(np.mean(recent_data**2))

                    # Convert to percentage (0-100)
                    # Calibrated for normal speech levels
                    level_percent = min(100, int(rms * 3500))

                    self.current_level = level_percent
                    self.level_bar.setValue(level_percent)

                    # Update status based on level
                    if level_percent < 5:
                        self.status_label.setText("Microphone Quality: No signal detected")
                        self.status_label.setStyleSheet("color: red; font-size: 12px;")
                    elif level_percent < 20:
                        self.status_label.setText("Microphone Quality: Very weak signal")
                        self.status_label.setStyleSheet("color: orange; font-size: 12px;")
                    elif level_percent < 40:
                        self.status_label.setText("Microphone Quality: Good")
                        self.status_label.setStyleSheet("color: green; font-size: 12px; font-weight: bold;")
                    else:
                        self.status_label.setText("Microphone Quality: Excellent")
                        self.status_label.setStyleSheet("color: darkgreen; font-size: 12px; font-weight: bold;")

        except Exception as e:
            pass  # Ignore errors during level checking

    def close_and_stop(self):
        """Stop monitoring and close dialog."""
        if self.is_recording:
            self.update_timer.stop()
            self.audio_recorder.stop_recording()
            self.is_recording = False
        self.accept()

    def closeEvent(self, event):
        """Handle dialog close event."""
        self.close_and_stop()
        event.accept()
