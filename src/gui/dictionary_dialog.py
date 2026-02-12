"""
Custom dictionary dialog for Resonance.
Allows users to map multiple misheard variations to the correct word.
Includes "Learn from Voice" — record yourself saying a word and let Whisper
discover what it hears, auto-adding the result as a variation.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QListWidget, QListWidgetItem,
    QHeaderView, QMessageBox, QCheckBox, QGroupBox,
    QSplitter, QWidget
)
from PySide6.QtCore import Signal, Qt, QThread, QTimer, QObject


class LearnWorker(QObject):
    """Worker that transcribes a short audio clip in a background thread."""

    finished = Signal(str)   # transcribed text
    error = Signal(str)

    def __init__(self, transcriber, audio_data):
        super().__init__()
        self.transcriber = transcriber
        self.audio_data = audio_data

    def run(self):
        try:
            text = self.transcriber.transcribe(self.audio_data)
            self.finished.emit(text.strip())
        except Exception as e:
            self.error.emit(str(e))


class DictionaryDialog(QDialog):
    """Dialog for managing custom word replacements (many-to-one)."""

    dictionary_changed = Signal()

    def __init__(self, config_manager, audio_recorder, transcriber, parent=None):
        super().__init__(parent)
        self.config = config_manager
        self.audio_recorder = audio_recorder
        self.transcriber = transcriber

        # Learn-from-voice state
        self._is_recording = False
        self._learn_thread = None
        self._learn_worker = None
        self._record_timer = None

        self.setWindowTitle("Custom Dictionary")
        self.setMinimumWidth(650)
        self.setMinimumHeight(520)

        self.init_ui()
        self.load_dictionary()

    def init_ui(self):
        """Initialize user interface."""
        layout = QVBoxLayout()

        # Description
        desc = QLabel(
            "Add correct words on the left. Then use \"Learn from Voice\" to say\n"
            "the word — Whisper will show what it hears, and that gets auto-added\n"
            "as a variation. Repeat a few times to catch different interpretations."
        )
        desc.setStyleSheet("color: gray; font-size: 11px; margin-bottom: 8px;")
        layout.addWidget(desc)

        # Enable/disable checkbox
        self.enabled_checkbox = QCheckBox("Enable custom dictionary")
        self.enabled_checkbox.setChecked(True)
        layout.addWidget(self.enabled_checkbox)

        # Main splitter: left = correct words, right = variations for selected word
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- Left panel: Correct words ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        left_label = QLabel("Correct Words")
        left_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        left_layout.addWidget(left_label)

        self.word_list = QListWidget()
        self.word_list.currentItemChanged.connect(self.on_word_selected)
        left_layout.addWidget(self.word_list)

        # Add correct word
        add_word_layout = QHBoxLayout()
        self.new_word_input = QLineEdit()
        self.new_word_input.setPlaceholderText("e.g. iObeya")
        self.new_word_input.returnPressed.connect(self.add_word)
        add_word_layout.addWidget(self.new_word_input)

        self.add_word_button = QPushButton("Add")
        self.add_word_button.setFixedWidth(60)
        self.add_word_button.clicked.connect(self.add_word)
        add_word_layout.addWidget(self.add_word_button)

        left_layout.addLayout(add_word_layout)

        self.remove_word_button = QPushButton("Remove Word")
        self.remove_word_button.clicked.connect(self.remove_word)
        left_layout.addWidget(self.remove_word_button)

        splitter.addWidget(left_widget)

        # --- Right panel: Wrong variations for selected word ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.variations_label = QLabel("Wrong Variations")
        self.variations_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        right_layout.addWidget(self.variations_label)

        self.variation_list = QListWidget()
        right_layout.addWidget(self.variation_list)

        # --- Learn from Voice section ---
        learn_group = QGroupBox("Learn from Voice")
        learn_layout = QVBoxLayout()

        learn_desc = QLabel("Say the word into your mic — Whisper will show what it hears.")
        learn_desc.setStyleSheet("color: gray; font-size: 10px;")
        learn_layout.addWidget(learn_desc)

        record_row = QHBoxLayout()
        self.record_button = QPushButton("Record Sample (3s)")
        self.record_button.clicked.connect(self.toggle_recording)
        record_row.addWidget(self.record_button)

        self.learn_status = QLabel("")
        self.learn_status.setStyleSheet("font-size: 11px;")
        record_row.addWidget(self.learn_status)
        record_row.addStretch()

        learn_layout.addLayout(record_row)
        learn_group.setLayout(learn_layout)
        right_layout.addWidget(learn_group)

        # --- Manual add variation ---
        manual_group = QGroupBox("Add Manually")
        manual_layout = QHBoxLayout()
        self.new_variation_input = QLineEdit()
        self.new_variation_input.setPlaceholderText("e.g. IOBARE")
        self.new_variation_input.returnPressed.connect(self.add_variation)
        manual_layout.addWidget(self.new_variation_input)

        self.add_variation_button = QPushButton("Add")
        self.add_variation_button.setFixedWidth(60)
        self.add_variation_button.clicked.connect(self.add_variation)
        manual_layout.addWidget(self.add_variation_button)
        manual_group.setLayout(manual_layout)
        right_layout.addWidget(manual_group)

        self.remove_variation_button = QPushButton("Remove Selected Variation")
        self.remove_variation_button.clicked.connect(self.remove_variation)
        right_layout.addWidget(self.remove_variation_button)

        splitter.addWidget(right_widget)
        splitter.setSizes([230, 420])

        layout.addWidget(splitter)

        # Save / Cancel buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self.save_dictionary)
        button_layout.addWidget(self.save_button)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)

        self.setLayout(layout)

        # Disable right panel until a word is selected
        self._set_variations_enabled(False)

    def _set_variations_enabled(self, enabled):
        """Enable or disable the variations panel."""
        self.variation_list.setEnabled(enabled)
        self.new_variation_input.setEnabled(enabled)
        self.add_variation_button.setEnabled(enabled)
        self.remove_variation_button.setEnabled(enabled)
        self.record_button.setEnabled(enabled)

    # ---- Dictionary data management ----

    def load_dictionary(self):
        """Load dictionary from config."""
        self.enabled_checkbox.setChecked(self.config.get_dictionary_enabled())

        replacements = self.config.get_dictionary_replacements()
        self.word_list.clear()

        # Store variations data keyed by correct word
        self._data = {}

        for correct_word, variations in replacements.items():
            if isinstance(variations, list):
                self._data[correct_word] = list(variations)
            else:
                self._data[correct_word] = [variations] if variations else []
            self.word_list.addItem(correct_word)

        if self.word_list.count() > 0:
            self.word_list.setCurrentRow(0)

    def on_word_selected(self, current, previous):
        """Called when a correct word is selected — show its variations."""
        if current is None:
            self.variation_list.clear()
            self.variations_label.setText("Wrong Variations")
            self._set_variations_enabled(False)
            return

        word = current.text()
        self.variations_label.setText(f"Wrong Variations for \"{word}\"")
        self._set_variations_enabled(True)

        self.variation_list.clear()
        for var in self._data.get(word, []):
            self.variation_list.addItem(var)

    def add_word(self):
        """Add a new correct word."""
        word = self.new_word_input.text().strip()
        if not word:
            return

        for i in range(self.word_list.count()):
            if self.word_list.item(i).text().lower() == word.lower():
                QMessageBox.warning(
                    self, "Duplicate",
                    f"\"{word}\" is already in the dictionary."
                )
                return

        self._data[word] = []
        self.word_list.addItem(word)
        self.word_list.setCurrentRow(self.word_list.count() - 1)
        self.new_word_input.clear()

    def remove_word(self):
        """Remove the selected correct word and all its variations."""
        current = self.word_list.currentItem()
        if not current:
            QMessageBox.warning(self, "No Selection", "Select a word to remove.")
            return

        word = current.text()
        reply = QMessageBox.question(
            self, "Remove Word",
            f"Remove \"{word}\" and all its variations?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            del self._data[word]
            self.word_list.takeItem(self.word_list.row(current))

    def _try_add_variation(self, correct_word, variation):
        """
        Try to add a variation for a correct word.
        Returns True if added, False if skipped (duplicate, conflict, same word).
        """
        variation = variation.strip()
        if not variation:
            return False

        # Skip if it's the correct word itself
        if variation.lower() == correct_word.lower():
            return False

        # Skip duplicates for this word
        variations = self._data.get(correct_word, [])
        if any(v.lower() == variation.lower() for v in variations):
            return False

        # Skip if used by another word
        for other_word, other_vars in self._data.items():
            if other_word == correct_word:
                continue
            if any(v.lower() == variation.lower() for v in other_vars):
                return False

        self._data[correct_word].append(variation)
        return True

    def add_variation(self):
        """Add a wrong variation manually for the currently selected correct word."""
        current_word_item = self.word_list.currentItem()
        if not current_word_item:
            return

        variation = self.new_variation_input.text().strip()
        if not variation:
            return

        correct_word = current_word_item.text()

        if variation.lower() == correct_word.lower():
            QMessageBox.warning(
                self, "Same Word",
                "The variation can't be the same as the correct word."
            )
            return

        variations = self._data.get(correct_word, [])
        if any(v.lower() == variation.lower() for v in variations):
            QMessageBox.warning(
                self, "Duplicate",
                f"\"{variation}\" is already listed as a variation."
            )
            return

        for other_word, other_vars in self._data.items():
            if other_word == correct_word:
                continue
            if any(v.lower() == variation.lower() for v in other_vars):
                QMessageBox.warning(
                    self, "Conflict",
                    f"\"{variation}\" is already a variation of \"{other_word}\"."
                )
                return

        self._data[correct_word].append(variation)
        self.variation_list.addItem(variation)
        self.new_variation_input.clear()
        self.new_variation_input.setFocus()

    def remove_variation(self):
        """Remove the selected variation."""
        current_word_item = self.word_list.currentItem()
        var_item = self.variation_list.currentItem()
        if not current_word_item or not var_item:
            QMessageBox.warning(self, "No Selection", "Select a variation to remove.")
            return

        correct_word = current_word_item.text()
        variation = var_item.text()
        self._data[correct_word].remove(variation)
        self.variation_list.takeItem(self.variation_list.row(var_item))

    # ---- Learn from Voice ----

    def toggle_recording(self):
        """Start or stop a learning recording."""
        if self._is_recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        """Start recording a voice sample."""
        current_word_item = self.word_list.currentItem()
        if not current_word_item:
            QMessageBox.warning(
                self, "No Word Selected",
                "Select or add a correct word first, then record."
            )
            return

        try:
            self.audio_recorder.start_recording()
        except Exception as e:
            self.learn_status.setText(f"Mic error: {e}")
            self.learn_status.setStyleSheet("color: red; font-size: 11px;")
            return

        self._is_recording = True
        self.record_button.setText("Stop Recording")
        self.record_button.setStyleSheet("background-color: #e74c3c; color: white;")
        self.learn_status.setText("Listening... say the word now")
        self.learn_status.setStyleSheet("color: #e74c3c; font-weight: bold; font-size: 11px;")

        # Auto-stop after 3 seconds
        self._record_timer = QTimer(self)
        self._record_timer.setSingleShot(True)
        self._record_timer.timeout.connect(self._stop_recording)
        self._record_timer.start(3000)

    def _stop_recording(self):
        """Stop recording and transcribe the sample."""
        if not self._is_recording:
            return

        self._is_recording = False

        if self._record_timer:
            self._record_timer.stop()
            self._record_timer = None

        self.record_button.setText("Record Sample (3s)")
        self.record_button.setStyleSheet("")
        self.record_button.setEnabled(False)

        audio_data = self.audio_recorder.stop_recording()

        if audio_data is None or len(audio_data) == 0:
            self.learn_status.setText("No audio captured — try again")
            self.learn_status.setStyleSheet("color: orange; font-size: 11px;")
            self.record_button.setEnabled(True)
            return

        self.learn_status.setText("Transcribing...")
        self.learn_status.setStyleSheet("color: #2980b9; font-size: 11px;")

        # Transcribe in background thread
        self._learn_thread = QThread()
        self._learn_worker = LearnWorker(self.transcriber, audio_data)
        self._learn_worker.moveToThread(self._learn_thread)

        self._learn_thread.started.connect(self._learn_worker.run)
        self._learn_worker.finished.connect(self._on_learn_result)
        self._learn_worker.error.connect(self._on_learn_error)
        self._learn_worker.finished.connect(
            self._cleanup_learn_thread, Qt.ConnectionType.QueuedConnection
        )
        self._learn_worker.error.connect(
            self._cleanup_learn_thread, Qt.ConnectionType.QueuedConnection
        )

        self._learn_thread.start()

    def _on_learn_result(self, text):
        """Handle transcription result from a voice learning sample."""
        self.record_button.setEnabled(True)

        current_word_item = self.word_list.currentItem()
        if not current_word_item:
            self.learn_status.setText("No word selected")
            self.learn_status.setStyleSheet("color: orange; font-size: 11px;")
            return

        if not text:
            self.learn_status.setText("Nothing detected — try again")
            self.learn_status.setStyleSheet("color: orange; font-size: 11px;")
            return

        correct_word = current_word_item.text()

        # If Whisper heard the correct word exactly, no variation needed
        if text.strip().lower() == correct_word.lower():
            self.learn_status.setText(f"Whisper heard it correctly: \"{text}\"")
            self.learn_status.setStyleSheet("color: green; font-weight: bold; font-size: 11px;")
            return

        # Try to add it as a variation
        added = self._try_add_variation(correct_word, text)
        if added:
            self.variation_list.addItem(text)
            self.learn_status.setText(f"Added: \"{text}\"")
            self.learn_status.setStyleSheet("color: green; font-weight: bold; font-size: 11px;")
        else:
            self.learn_status.setText(f"Already known: \"{text}\"")
            self.learn_status.setStyleSheet("color: gray; font-size: 11px;")

    def _on_learn_error(self, error_msg):
        """Handle transcription error during voice learning."""
        self.record_button.setEnabled(True)
        self.learn_status.setText(f"Error: {error_msg}")
        self.learn_status.setStyleSheet("color: red; font-size: 11px;")

    def _cleanup_learn_thread(self, _result=None):
        """Clean up the background transcription thread."""
        if self._learn_thread:
            self._learn_thread.quit()
            self._learn_thread.wait(2000)
            self._learn_thread.deleteLater()
            self._learn_thread = None
        if self._learn_worker:
            self._learn_worker.deleteLater()
            self._learn_worker = None

    # ---- Save ----

    def save_dictionary(self):
        """Save dictionary to config."""
        # Filter out words with no variations
        replacements = {
            word: variations
            for word, variations in self._data.items()
            if variations
        }

        self.config.set_dictionary_enabled(self.enabled_checkbox.isChecked())
        self.config.set_dictionary_replacements(replacements)
        self.config.save()

        self.dictionary_changed.emit()

        total_variations = sum(len(v) for v in replacements.values())
        QMessageBox.information(
            self, "Dictionary Saved",
            f"Saved {len(replacements)} word(s) with {total_variations} total variation(s)."
        )
        self.accept()

    def closeEvent(self, event):
        """Clean up on close."""
        if self._is_recording:
            self.audio_recorder.stop_recording()
        self._cleanup_learn_thread()
        event.accept()
