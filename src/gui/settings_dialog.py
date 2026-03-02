"""
Settings dialog for Resonance.
Allows configuration of hotkey, model, audio device, etc.
"""

import os
import platform
import time
import webbrowser
from importlib.metadata import version as pkg_version, PackageNotFoundError
from urllib.parse import quote

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QGroupBox, QLineEdit,
    QFormLayout, QProgressBar, QRadioButton,
    QButtonGroup, QGridLayout, QFrame, QCheckBox,
    QScrollArea, QWidget
)
from PySide6.QtCore import Signal, QTimer, Qt, QThread, QObject
from PySide6.QtGui import QKeyEvent, QGuiApplication

from gui.dictionary_dialog import DictionaryDialog
from gui.theme import RoundedDialog, MessageBox
from utils.config import format_hotkey_display


class _NoWheelComboBox(QComboBox):
    """QComboBox that ignores mouse wheel events so scrolling passes through."""

    def wheelEvent(self, event):
        event.ignore()


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
            # Clean up any partial/failed downloads before retrying
            self.transcriber.clean_partial_download(self.model_size)

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
        self._timer.stop()
        # Disconnect worker signals so they can't fire into a destroyed dialog
        if self._worker:
            try:
                self._worker.finished.disconnect()
                self._worker.error.disconnect()
            except RuntimeError:
                pass
        if self._thread:
            self._thread.quit()
            if not self._thread.wait(3000):
                # Thread didn't stop (blocking network call) — detach it
                # so it can finish in the background without crashing
                self._thread.finished.connect(self._thread.deleteLater)
                if self._worker:
                    self._thread.finished.connect(self._worker.deleteLater)
                self._thread = None
                self._worker = None
                return
            self._thread.deleteLater()
            self._thread = None
        if self._worker:
            self._worker.deleteLater()
            self._worker = None

    def reject(self):
        self._cleanup()
        super().reject()

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
        self._tick_timer.stop()
        if self._worker:
            try:
                self._worker.finished.disconnect()
                self._worker.error.disconnect()
                self._worker.progress.disconnect()
            except RuntimeError:
                pass
        if self._thread:
            self._thread.quit()
            if not self._thread.wait(3000):
                self._thread.finished.connect(self._thread.deleteLater)
                if self._worker:
                    self._thread.finished.connect(self._worker.deleteLater)
                self._thread = None
                self._worker = None
                return
            self._thread.deleteLater()
            self._thread = None
        if self._worker:
            self._worker.deleteLater()
            self._worker = None

    def reject(self):
        self._cleanup()
        super().reject()

    def closeEvent(self, event):
        self._cleanup()
        event.accept()

    @property
    def succeeded(self):
        return self._success


class _SettingsUpdateCheckWorker(QObject):
    """Background worker for checking updates from settings dialog."""

    update_available = Signal(str, str, str)  # version, download_url, tag_name
    up_to_date = Signal()
    error = Signal(str)

    def run(self):
        try:
            from core.updater import UpdateChecker
            checker = UpdateChecker()
            info = checker.check_for_update()
            if info:
                self.update_available.emit(info.version_str, info.download_url, info.tag_name)
            else:
                self.up_to_date.emit()
        except Exception as e:
            self.error.emit(str(e))


class _SettingsUpdateDownloadWorker(QObject):
    """Background worker for downloading an update from settings dialog."""

    finished = Signal(str)  # downloaded file path
    error = Signal(str)
    progress = Signal(int, int)  # downloaded, total

    def __init__(self, version_str, download_url):
        super().__init__()
        self.version_str = version_str
        self.download_url = download_url

    def run(self):
        try:
            from core.updater import UpdateChecker, UpdateInfo
            checker = UpdateChecker()
            info = UpdateInfo(
                version_str=self.version_str,
                tag_name="",
                download_url=self.download_url,
            )
            path = checker.download_update(info, progress_callback=self._on_progress)
            if path:
                self.finished.emit(path)
            else:
                self.error.emit("Download failed")
        except Exception as e:
            self.error.emit(str(e))

    def _on_progress(self, downloaded, total):
        self.progress.emit(downloaded, total)


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
        self.setFixedWidth(800)

        self.init_ui()
        self.load_current_settings()

    def init_ui(self):
        """Initialize user interface."""
        outer_layout = QVBoxLayout()

        # Scroll area wrapping all group boxes (vertical only)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll_area.viewport().setStyleSheet("background: transparent;")

        content_widget = QWidget()
        content_widget.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(2, 0, 8, 0)

        # Usage statistics (dashboard cards at top)
        statistics_group = self.create_statistics_group()
        content_layout.addWidget(statistics_group)

        # Hotkey settings
        hotkey_group = self.create_hotkey_group()
        content_layout.addWidget(hotkey_group)

        # Whisper model settings
        model_group = self.create_model_group()
        content_layout.addWidget(model_group)

        # Audio settings
        audio_group = self.create_audio_group()
        content_layout.addWidget(audio_group)

        # Typing settings
        typing_group = self.create_typing_group()
        content_layout.addWidget(typing_group)

        # Dictionary settings
        dictionary_group = self.create_dictionary_group()
        content_layout.addWidget(dictionary_group)

        # Updates
        updates_group = self.create_updates_group()
        content_layout.addWidget(updates_group)

        # Bug report
        bug_report_group = self.create_bug_report_group()
        content_layout.addWidget(bug_report_group)

        content_widget.setLayout(content_layout)
        scroll_area.setWidget(content_widget)
        outer_layout.addWidget(scroll_area, 1)

        # Buttons (fixed at bottom, outside scroll area)
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self.save_settings)
        button_layout.addWidget(self.save_button)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        outer_layout.addLayout(button_layout)

        self.setLayout(outer_layout)

    def showEvent(self, event):
        """Size dialog to fit content width and constrain height to screen."""
        screen = self.screen()
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            hint = self.sizeHint()
            new_width = min(hint.width(), geo.width() - 40)
            new_height = min(hint.height(), geo.height() - 40)
            self.resize(new_width, new_height)
        super().showEvent(event)

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
        self.model_combo = _NoWheelComboBox()
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
            "Fixes grammar, capitalization, punctuation, contractions, quotations, and "
            "sentence breaks. Removes filler words like \"um\" and \"uh\", and cleans up "
            "stuttered repeats. Runs entirely on your machine using Qwen 2.5 — no data "
            "leaves your computer. Required for On-Screen Recognition and Self-Learning."
        )
        pp_desc.setWordWrap(True)
        pp_desc.setStyleSheet("color: rgba(255, 255, 255, 140); font-size: 11px;")

        pp_col = QVBoxLayout()
        pp_col.setSpacing(2)
        pp_col.addWidget(self.post_processing_cb)
        pp_col.addWidget(pp_desc)
        layout.addRow("", pp_col)

        # On-Screen Recognition checkbox + description
        self.ocr_cb = QCheckBox("On-Screen Recognition (OSR)")
        self._ocr_label_base = "On-Screen Recognition (OSR)"
        ocr_desc = QLabel(
            "Takes a screenshot of your active window each time you dictate to identify "
            "the app you're using (chat, email, code, document) and extract names visible "
            "on screen. Dictation formatting automatically adapts — casual in Discord, "
            "professional in Outlook, technical in VS Code. Names on screen are used as "
            "pronunciation hints so Whisper spells them correctly."
        )
        ocr_desc.setWordWrap(True)
        ocr_desc.setStyleSheet("color: rgba(255, 255, 255, 140); font-size: 11px;")

        ocr_col = QVBoxLayout()
        ocr_col.setSpacing(2)
        ocr_col.addWidget(self.ocr_cb)
        ocr_col.addWidget(ocr_desc)
        layout.addRow("", ocr_col)

        # Self-Learning Recognition checkbox + description
        self.learning_cb = QCheckBox("Self-Learning Recognition")
        self._learning_label_base = "Self-Learning Recognition"
        learning_desc = QLabel(
            "Builds a profile for each app you use over time. Learns which names appear "
            "frequently, how formal the communication style is, and what kind of vocabulary "
            "you encounter. The more you dictate, the better it gets — adapting punctuation, "
            "capitalization, and word hints to match each app's style. No conversations are "
            "stored, only statistical patterns."
        )
        learning_desc.setWordWrap(True)
        learning_desc.setStyleSheet("color: rgba(255, 255, 255, 140); font-size: 11px;")

        learning_col = QVBoxLayout()
        learning_col.setSpacing(2)
        learning_col.addWidget(self.learning_cb)
        learning_col.addWidget(learning_desc)
        layout.addRow("", learning_col)

        # Dependency chain: PP → OSR → Self-Learning
        self.post_processing_cb.stateChanged.connect(self._on_pp_toggled)
        self.ocr_cb.stateChanged.connect(self._on_ocr_toggled)

        group.setLayout(layout)
        return group

    def _on_pp_toggled(self, state):
        """Enable/disable OCR checkbox based on post-processing state."""
        if not self.post_processing_cb.isChecked():
            self.ocr_cb.setChecked(False)
            self.ocr_cb.setEnabled(False)
            self.ocr_cb.setText(f"{self._ocr_label_base} (requires Post-Processing)")
        else:
            self.ocr_cb.setEnabled(True)
            self.ocr_cb.setText(self._ocr_label_base)
        # Cascade: OSR state affects self-learning
        self._on_ocr_toggled()

    def _on_ocr_toggled(self, state=None):
        """Enable/disable Self-Learning Recognition checkbox based on OSR state."""
        if not self.ocr_cb.isChecked() or not self.ocr_cb.isEnabled():
            self.learning_cb.setChecked(False)
            self.learning_cb.setEnabled(False)
            self.learning_cb.setText(f"{self._learning_label_base} (requires Post-Processing and OSR)")
        else:
            self.learning_cb.setEnabled(True)
            self.learning_cb.setText(self._learning_label_base)

    def create_audio_group(self):
        """Create audio device configuration group."""
        group = QGroupBox("Audio Settings")
        layout = QFormLayout()

        # Audio device dropdown
        self.device_combo = _NoWheelComboBox()
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

    def create_updates_group(self):
        """Create updates group with version display and check button."""
        group = QGroupBox("Updates")
        layout = QVBoxLayout()

        # Current version
        try:
            current_ver = pkg_version("resonance")
        except PackageNotFoundError:
            current_ver = "dev"

        version_label = QLabel(f"Current version: {current_ver}")
        version_label.setStyleSheet("font-size: 12px; font-weight: bold;")
        layout.addWidget(version_label)

        # Status label (hidden until check performed)
        self._update_status = QLabel("")
        self._update_status.setStyleSheet("color: rgba(255, 255, 255, 140); font-size: 11px;")
        self._update_status.hide()
        layout.addWidget(self._update_status)

        # Buttons row
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        # "Download and Install" button — hidden by default, shown when update found
        self._update_download_btn = QPushButton("Download and Install")
        self._update_download_btn.hide()
        self._update_download_btn.clicked.connect(self._download_update)
        button_layout.addWidget(self._update_download_btn)

        # "Check for Updates" button
        self._update_check_btn = QPushButton("Check for Updates")
        self._update_check_btn.clicked.connect(self._check_for_updates)
        button_layout.addWidget(self._update_check_btn)

        layout.addLayout(button_layout)

        # Source install hint (hidden until update found on non-bundled)
        self._update_source_hint = QLabel("")
        self._update_source_hint.setStyleSheet("color: rgba(255, 255, 255, 140); font-size: 11px;")
        self._update_source_hint.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._update_source_hint.hide()
        layout.addWidget(self._update_source_hint)

        # Stash for download info
        self._pending_update_version = None
        self._pending_update_url = None

        group.setLayout(layout)
        return group

    def _check_for_updates(self):
        """Run update check in background thread."""
        self._update_check_btn.setEnabled(False)
        self._update_status.setText("Checking...")
        self._update_status.show()

        thread = QThread()
        worker = _SettingsUpdateCheckWorker()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)

        def _on_update(version_str, download_url, tag_name):
            try:
                thread.quit()
                self._update_check_btn.setEnabled(True)
                self._update_status.setText(f"Resonance {version_str} is available!")
                self._update_status.setStyleSheet("color: #2ecc71; font-size: 11px; font-weight: bold;")
                self._pending_update_version = version_str
                self._pending_update_url = download_url

                from utils.resource_path import is_bundled
                if is_bundled():
                    self._update_download_btn.show()
                else:
                    self._update_source_hint.setText(f"Run: git pull && uv sync")
                    self._update_source_hint.show()
            except Exception as e:
                print(f"Update check callback error: {e}")

        def _on_up_to_date():
            thread.quit()
            self._update_check_btn.setEnabled(True)
            self._update_status.setText("Up to date!")
            self._update_status.setStyleSheet("color: rgba(255, 255, 255, 140); font-size: 11px;")

        def _on_error(msg):
            thread.quit()
            self._update_check_btn.setEnabled(True)
            self._update_status.setText(f"Check failed: {msg}")

        worker.update_available.connect(_on_update, Qt.ConnectionType.QueuedConnection)
        worker.up_to_date.connect(_on_up_to_date, Qt.ConnectionType.QueuedConnection)
        worker.error.connect(_on_error, Qt.ConnectionType.QueuedConnection)

        # Keep references
        self._update_check_thread = thread
        self._update_check_worker = worker

        thread.start()

    def _download_update(self):
        """Download and apply update via progress dialog."""
        if not self._pending_update_version or not self._pending_update_url:
            return

        version_str = self._pending_update_version
        download_url = self._pending_update_url

        # Create progress dialog
        dlg = RoundedDialog(self)
        dlg.setWindowTitle("Updating Resonance")
        dlg.setMinimumWidth(420)

        d_layout = QVBoxLayout()
        d_layout.setSpacing(12)
        d_status = QLabel(f"Downloading Resonance {version_str}...")
        d_status.setStyleSheet("font-size: 12px;")
        d_layout.addWidget(d_status)

        d_bar = QProgressBar()
        d_bar.setMinimum(0)
        d_bar.setMaximum(100)
        d_bar.setValue(0)
        d_bar.setTextVisible(True)
        d_bar.setFormat("%v%")
        d_bar.setMinimumHeight(28)
        d_layout.addWidget(d_bar)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dlg.reject)
        btn_layout.addWidget(cancel_btn)
        d_layout.addLayout(btn_layout)

        dlg.setLayout(d_layout)

        thread = QThread()
        worker = _SettingsUpdateDownloadWorker(version_str, download_url)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)

        def _on_progress(downloaded, total):
            if total > 0:
                pct = min(99, int(downloaded / total * 100))
                d_bar.setValue(pct)
                mb_done = downloaded / (1024 * 1024)
                mb_total = total / (1024 * 1024)
                d_status.setText(f"Downloading Resonance {version_str}... {mb_done:.1f} / {mb_total:.1f} MB")

        def _on_finished(path):
            d_bar.setValue(100)
            thread.quit()
            dlg.accept()
            from core.updater import UpdateChecker
            checker = UpdateChecker()
            if checker.apply_update(path):
                # Close settings dialog and quit app for restart
                self.reject()
                from PySide6.QtWidgets import QApplication
                QApplication.quit()

        def _on_error(msg):
            thread.quit()
            d_status.setText(f"Download failed: {msg}")

        worker.progress.connect(_on_progress, Qt.ConnectionType.QueuedConnection)
        worker.finished.connect(_on_finished, Qt.ConnectionType.QueuedConnection)
        worker.error.connect(_on_error, Qt.ConnectionType.QueuedConnection)

        dlg._dl_thread = thread
        dlg._dl_worker = worker

        thread.start()
        dlg.exec()

    def create_bug_report_group(self):
        """Create bug report group box."""
        group = QGroupBox("Bug Report")
        layout = QVBoxLayout()

        info_label = QLabel(
            "Experiencing an issue? Submit a bug report with your system info and recent logs."
        )
        info_label.setStyleSheet("color: rgba(255, 255, 255, 140); font-size: 11px;")
        layout.addWidget(info_label)

        button_layout = QHBoxLayout()
        button_layout.addStretch()

        report_button = QPushButton("Report Bug...")
        report_button.clicked.connect(self._open_bug_report)
        button_layout.addWidget(report_button)

        layout.addLayout(button_layout)

        group.setLayout(layout)
        return group

    def _open_bug_report(self):
        """Collect system info and open a pre-filled GitHub issue in the browser."""
        # App version
        try:
            app_version = pkg_version("resonance")
        except PackageNotFoundError:
            app_version = "dev"

        # Model display name
        model_id = self.config.get_model_size()
        model_names = {"tiny": "Fastest", "base": "Balanced", "small": "Accurate", "medium": "Precision"}
        model_display = f"{model_names.get(model_id, model_id)} ({model_id})"

        # Post-processing
        pp_status = "On" if self.config.get_post_processing_enabled() else "Off"

        # Entry method
        use_clipboard = self.config.get("typing", "use_clipboard_fallback", default=False)
        entry_method = "Clipboard" if use_clipboard else "Character-by-character"

        # Audio device
        device = self.config.get_audio_device()
        audio_device = "System Default" if device is None else str(device)

        # Recent logs
        from utils.resource_path import get_app_data_path
        log_path = os.path.join(get_app_data_path("logs"), "resonance.log")
        log_lines = ""
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
                log_lines = "".join(all_lines[-50:])
        except (OSError, FileNotFoundError):
            log_lines = "(no log file found)"

        # Build body
        def _build_body(logs):
            return (
                "## Description\n"
                "[Describe the issue here]\n\n"
                "## Steps to Reproduce\n"
                "1. \n2. \n3. \n\n"
                "## Expected Behavior\n\n\n"
                "## System Info\n"
                f"- **App Version**: {app_version}\n"
                f"- **OS**: {platform.platform()}\n"
                f"- **Python**: {platform.python_version()}\n"
                f"- **Model**: {model_display}\n"
                f"- **Post-Processing**: {pp_status}\n"
                f"- **Entry Method**: {entry_method}\n"
                f"- **Audio Device**: {audio_device}\n\n"
                "## Recent Logs\n"
                "```\n"
                f"{logs}"
                "```\n"
            )

        body = _build_body(log_lines)

        # Truncate body to keep URL under ~8000 chars
        max_body = 6000
        if len(body) > max_body:
            truncation_note = "\n... (truncated)\n```\n"
            overhead = len(body) - len(log_lines)
            allowed_log = max_body - overhead - len(truncation_note)
            log_lines = log_lines[:allowed_log] + truncation_note
            body = _build_body(log_lines)

        title = quote("Bug: ")
        encoded_body = quote(body)
        url = f"https://github.com/whorne89/Resonance/issues/new?title={title}&body={encoded_body}"

        webbrowser.open(url)

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

    def _load_learning_stats(self):
        """Load learning stats from the profiles JSON file."""
        import json
        from utils.resource_path import get_app_data_path
        from pathlib import Path

        result = {"apps_learned": 0, "words_learned": 0, "top_app": "—", "avg_confidence": "—"}
        profiles_path = Path(get_app_data_path("learning")) / "app_profiles.json"
        if not profiles_path.exists():
            return result

        try:
            with open(profiles_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            profiles = data.get("profiles", {})
            result["apps_learned"] = len(profiles)

            top_sessions = 0
            total_confidence = 0.0
            for p in profiles.values():
                result["words_learned"] += len(p.get("vocabulary", []))
                sessions = p.get("sessions", 0)
                if sessions > top_sessions:
                    top_sessions = sessions
                    result["top_app"] = p.get("display_name", p.get("app_key", "—"))
                total_confidence += p.get("confidence", 0.0)

            if profiles:
                avg = total_confidence / len(profiles)
                result["avg_confidence"] = f"{avg:.0%}"
        except Exception:
            pass
        return result

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

        # Build stat cards grid (4 columns)
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

        # Learning stats from profiles JSON
        learning_stats = self._load_learning_stats()
        cards += [
            ("Apps Learned",     f"{learning_stats['apps_learned']:,}"),
            ("Words Learned",    f"{learning_stats['words_learned']:,}"),
            ("Top App",          learning_stats['top_app']),
            ("Avg Confidence",   learning_stats['avg_confidence']),
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

        # OCR screen context
        self.ocr_cb.setChecked(self.config.get_ocr_enabled())
        if not self.config.get_post_processing_enabled():
            self.ocr_cb.setEnabled(False)
            self.ocr_cb.setText(f"{self._ocr_label_base} (requires Post-Processing)")

        # Self-Learning Recognition
        self.learning_cb.setChecked(self.config.get_learning_enabled())
        if not self.config.get_ocr_enabled() or not self.config.get_post_processing_enabled():
            self.learning_cb.setEnabled(False)
            self.learning_cb.setText(f"{self._learning_label_base} (requires Post-Processing and OSR)")

    def save_settings(self):
        """Save settings and emit signal."""
        try:
            # Get values from UI
            hotkey = self.hotkey_display.text().strip().lower()
            model_size = self.model_combo.currentData()
            device_idx = self.device_combo.currentData()
            use_clipboard = self.typing_paste_radio.isChecked()
            pp_enabled = self.post_processing_cb.isChecked()
            ocr_enabled = self.ocr_cb.isChecked()
            learning_enabled = self.learning_cb.isChecked()

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
            old_ocr = self.config.get_ocr_enabled()
            old_learning = self.config.get_learning_enabled()

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
            if ocr_enabled != old_ocr:
                changes.append(f"OSR \u2192 {'On' if ocr_enabled else 'Off'}")
            if learning_enabled != old_learning:
                changes.append(f"Self-Learning \u2192 {'On' if learning_enabled else 'Off'}")

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
                        # Revert combo to the previously saved model
                        old_index = self.model_combo.findData(old_model)
                        if old_index >= 0:
                            self.model_combo.setCurrentIndex(old_index)
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
            self.config.set_ocr_enabled(ocr_enabled)
            self.config.set_learning_enabled(learning_enabled)
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
