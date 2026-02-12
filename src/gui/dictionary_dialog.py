"""
Custom dictionary dialog for Resonance.
Allows users to map multiple misheard variations to the correct word.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QListWidget, QListWidgetItem,
    QHeaderView, QMessageBox, QCheckBox, QGroupBox,
    QSplitter, QWidget
)
from PySide6.QtCore import Signal, Qt


class DictionaryDialog(QDialog):
    """Dialog for managing custom word replacements (many-to-one)."""

    dictionary_changed = Signal()

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config = config_manager

        self.setWindowTitle("Custom Dictionary")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)

        self.init_ui()
        self.load_dictionary()

    def init_ui(self):
        """Initialize user interface."""
        layout = QVBoxLayout()

        # Description
        desc = QLabel(
            "Add correct words on the left, then add all the wrong ways Whisper\n"
            "might hear them on the right. Each wrong variation will be auto-corrected."
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

        # Add variation
        add_var_layout = QHBoxLayout()
        self.new_variation_input = QLineEdit()
        self.new_variation_input.setPlaceholderText("e.g. IOBARE")
        self.new_variation_input.returnPressed.connect(self.add_variation)
        add_var_layout.addWidget(self.new_variation_input)

        self.add_variation_button = QPushButton("Add")
        self.add_variation_button.setFixedWidth(60)
        self.add_variation_button.clicked.connect(self.add_variation)
        add_var_layout.addWidget(self.add_variation_button)

        right_layout.addLayout(add_var_layout)

        self.remove_variation_button = QPushButton("Remove Variation")
        self.remove_variation_button.clicked.connect(self.remove_variation)
        right_layout.addWidget(self.remove_variation_button)

        splitter.addWidget(right_widget)
        splitter.setSizes([250, 350])

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
                # Handle old format (single string) gracefully
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

        # Check for duplicate
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
        self.new_variation_input.setFocus()

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

    def add_variation(self):
        """Add a wrong variation for the currently selected correct word."""
        current_word_item = self.word_list.currentItem()
        if not current_word_item:
            return

        variation = self.new_variation_input.text().strip()
        if not variation:
            return

        correct_word = current_word_item.text()

        # Don't allow adding the correct word itself as a variation
        if variation.lower() == correct_word.lower():
            QMessageBox.warning(
                self, "Same Word",
                "The variation can't be the same as the correct word."
            )
            return

        # Check for duplicate in this word's variations
        variations = self._data.get(correct_word, [])
        if any(v.lower() == variation.lower() for v in variations):
            QMessageBox.warning(
                self, "Duplicate",
                f"\"{variation}\" is already listed as a variation."
            )
            return

        # Check if this variation is already used by another correct word
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
