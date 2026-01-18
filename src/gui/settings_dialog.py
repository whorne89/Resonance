"""
Settings dialog for Resonance.
Allows configuration of hotkey, model, audio device, etc.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QGroupBox, QLineEdit,
    QMessageBox, QFormLayout, QProgressBar
)
from PySide6.QtCore import Signal, QTimer, Qt
from PySide6.QtGui import QPalette, QColor, QKeyEvent


class HotkeyCaptureDialog(QDialog):
    """Dialog for capturing hotkey combinations."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.captured_hotkey = None
        self.pressed_modifiers = set()
        self.pressed_key = None

        self.setWindowTitle("Capture Hotkey")
        self.setModal(True)
        self.setMinimumWidth(400)
        self.setMinimumHeight(150)

        # Set window flags to stay on top
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint)

        layout = QVBoxLayout()

        # Instruction label
        self.instruction_label = QLabel("Press any key combination...")
        self.instruction_label.setStyleSheet("font-size: 14px; font-weight: bold; padding: 20px;")
        self.instruction_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.instruction_label)

        # Display label for showing current combination
        self.display_label = QLabel("")
        self.display_label.setStyleSheet("font-size: 18px; color: #0066cc; padding: 10px;")
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


class SettingsDialog(QDialog):
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

        # Hotkey settings
        hotkey_group = self.create_hotkey_group()
        layout.addWidget(hotkey_group)

        # Whisper model settings
        model_group = self.create_model_group()
        layout.addWidget(model_group)

        # Audio settings
        audio_group = self.create_audio_group()
        layout.addWidget(audio_group)

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
        self.hotkey_display.setStyleSheet("font-size: 12px; font-weight: bold; padding: 5px; border: 1px solid #ccc; border-radius: 3px; background-color: #f5f5f5;")
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
        help_label.setStyleSheet("color: gray; font-size: 10px;")
        layout.addRow("", help_label)

        group.setLayout(layout)
        return group

    def capture_hotkey(self):
        """Open dialog to capture new hotkey."""
        dialog = HotkeyCaptureDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if dialog.captured_hotkey:
                self.hotkey_display.setText(dialog.captured_hotkey)

    def create_model_group(self):
        """Create Whisper model configuration group."""
        group = QGroupBox("Whisper Model Settings")
        layout = QFormLayout()

        # Model size dropdown
        self.model_combo = QComboBox()
        models = ["tiny", "base", "small", "medium", "large"]
        self.model_combo.addItems(models)
        layout.addRow("Model Size:", self.model_combo)

        # Model info
        info_label = QLabel(
            "tiny: Fastest, lower accuracy (~70MB)\n"
            "base: Fast, decent accuracy (~140MB)\n"
            "small: Balanced (recommended) (~500MB)\n"
            "medium: Better accuracy (~1.5GB)\n"
            "large: Best accuracy (~3GB)"
        )
        info_label.setStyleSheet("color: gray; font-size: 10px;")
        layout.addRow("", info_label)

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
        hotkey = self.config.get_hotkey()
        self.hotkey_display.setText(hotkey)

        # Model size
        model_size = self.config.get_model_size()
        index = self.model_combo.findText(model_size)
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

    def save_settings(self):
        """Save settings and emit signal."""
        try:
            # Get values from UI
            hotkey = self.hotkey_display.text().strip()
            model_size = self.model_combo.currentText()
            device_idx = self.device_combo.currentData()

            # Validate hotkey (just check it's not empty)
            if not hotkey:
                QMessageBox.warning(
                    self,
                    "Invalid Hotkey",
                    "Please set a hotkey combination using the 'Change Hotkey' button."
                )
                return

            # Check if model changed and needs downloading
            current_model = self.config.get_model_size()
            model_will_download = False

            if model_size != current_model:
                if not self.transcriber.is_model_downloaded(model_size):
                    # Model not downloaded - ask user if they want to proceed
                    model_info = self.transcriber.get_model_size_info(model_size)
                    size_mb = model_info['size_mb']
                    size_gb = size_mb / 1000
                    size_str = f"{size_gb:.1f} GB" if size_mb >= 1000 else f"{size_mb} MB"

                    reply = QMessageBox.question(
                        self,
                        "Model Not Downloaded",
                        f"The '{model_size}' model (~{size_str}) is not downloaded yet.\n\n"
                        f"It will be downloaded automatically the first time you use it.\n"
                        f"This may take several minutes.\n\n"
                        f"Do you want to switch to this model?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.Yes
                    )

                    if reply == QMessageBox.StandardButton.No:
                        return

                    model_will_download = True

            # Save to config
            self.config.set_hotkey(hotkey)
            self.config.set_model_size(model_size)
            self.config.set_audio_device(device_idx)
            self.config.save()

            # Emit signal
            self.settings_changed.emit()

            # Show success message
            if model_will_download:
                QMessageBox.information(
                    self,
                    "Settings Saved",
                    f"Settings saved successfully.\n\n"
                    f"The '{model_size}' model will download automatically the first time you use it."
                )
            else:
                QMessageBox.information(
                    self,
                    "Settings Saved",
                    "Settings saved successfully."
                )

            self.accept()

        except Exception as e:
            QMessageBox.critical(
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
        meter_dialog.exec_()


class AudioLevelMeterDialog(QDialog):
    """Dialog showing real-time audio level meter."""

    def __init__(self, audio_recorder, parent=None):
        super().__init__(parent)
        self.audio_recorder = audio_recorder
        self.is_recording = False
        self.current_level = 0

        self.setWindowTitle("Microphone Test")
        self.setMinimumWidth(400)
        self.setMinimumHeight(200)

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
        instructions.setStyleSheet("color: gray; margin-bottom: 10px;")
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
                border: 2px solid grey;
                border-radius: 5px;
                text-align: center;
                background-color: #f0f0f0;
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
