"""
Custom dictionary dialog for Resonance.
Allows users to add word replacements to correct common transcription errors.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QCheckBox, QGroupBox
)
from PySide6.QtCore import Signal, Qt


class DictionaryDialog(QDialog):
    """Dialog for managing custom word replacements."""

    dictionary_changed = Signal()

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config = config_manager

        self.setWindowTitle("Custom Dictionary")
        self.setMinimumWidth(550)
        self.setMinimumHeight(450)

        self.init_ui()
        self.load_dictionary()

    def init_ui(self):
        """Initialize user interface."""
        layout = QVBoxLayout()

        # Description
        desc = QLabel(
            "Add words that Resonance commonly gets wrong. When the wrong word\n"
            "is detected in a transcription, it will be replaced with your correction."
        )
        desc.setStyleSheet("color: gray; font-size: 11px; margin-bottom: 8px;")
        layout.addWidget(desc)

        # Enable/disable checkbox
        self.enabled_checkbox = QCheckBox("Enable custom dictionary")
        self.enabled_checkbox.setChecked(True)
        layout.addWidget(self.enabled_checkbox)

        # Table of replacements
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Whisper Hears", "Replace With"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        layout.addWidget(self.table)

        # Add new entry section
        add_group = QGroupBox("Add New Entry")
        add_layout = QHBoxLayout()

        self.wrong_input = QLineEdit()
        self.wrong_input.setPlaceholderText("Wrong word (e.g. IOBARE)")
        add_layout.addWidget(self.wrong_input)

        arrow_label = QLabel("->")
        arrow_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        arrow_label.setFixedWidth(30)
        arrow_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        add_layout.addWidget(arrow_label)

        self.correct_input = QLineEdit()
        self.correct_input.setPlaceholderText("Correct word (e.g. iObeya)")
        add_layout.addWidget(self.correct_input)

        self.add_button = QPushButton("Add")
        self.add_button.clicked.connect(self.add_entry)
        self.add_button.setFixedWidth(70)
        add_layout.addWidget(self.add_button)

        add_group.setLayout(add_layout)
        layout.addWidget(add_group)

        # Allow Enter key to add entry
        self.correct_input.returnPressed.connect(self.add_entry)
        self.wrong_input.returnPressed.connect(lambda: self.correct_input.setFocus())

        # Remove button
        remove_layout = QHBoxLayout()
        remove_layout.addStretch()

        self.remove_button = QPushButton("Remove Selected")
        self.remove_button.clicked.connect(self.remove_entry)
        remove_layout.addWidget(self.remove_button)

        layout.addLayout(remove_layout)

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

    def load_dictionary(self):
        """Load dictionary from config into the table."""
        self.enabled_checkbox.setChecked(self.config.get_dictionary_enabled())

        replacements = self.config.get_dictionary_replacements()
        self.table.setRowCount(0)

        for wrong, correct in replacements.items():
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(wrong))
            self.table.setItem(row, 1, QTableWidgetItem(correct))

    def add_entry(self):
        """Add a new dictionary entry from the input fields."""
        wrong = self.wrong_input.text().strip()
        correct = self.correct_input.text().strip()

        if not wrong or not correct:
            QMessageBox.warning(
                self, "Missing Input",
                "Please enter both the wrong word and the correct replacement."
            )
            return

        if wrong.lower() == correct.lower():
            QMessageBox.warning(
                self, "Same Word",
                "The wrong word and correction are the same."
            )
            return

        # Check for duplicate
        for row in range(self.table.rowCount()):
            existing = self.table.item(row, 0).text()
            if existing.lower() == wrong.lower():
                QMessageBox.warning(
                    self, "Duplicate Entry",
                    f"'{wrong}' is already in the dictionary."
                )
                return

        # Add to table
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(wrong))
        self.table.setItem(row, 1, QTableWidgetItem(correct))

        # Clear inputs
        self.wrong_input.clear()
        self.correct_input.clear()
        self.wrong_input.setFocus()

    def remove_entry(self):
        """Remove the selected dictionary entry."""
        selected = self.table.selectedItems()
        if not selected:
            QMessageBox.warning(
                self, "No Selection",
                "Please select an entry to remove."
            )
            return

        row = selected[0].row()
        self.table.removeRow(row)

    def save_dictionary(self):
        """Save dictionary to config."""
        replacements = {}
        for row in range(self.table.rowCount()):
            wrong = self.table.item(row, 0).text().strip()
            correct = self.table.item(row, 1).text().strip()
            if wrong and correct:
                replacements[wrong] = correct

        self.config.set_dictionary_enabled(self.enabled_checkbox.isChecked())
        self.config.set_dictionary_replacements(replacements)
        self.config.save()

        self.dictionary_changed.emit()

        QMessageBox.information(
            self, "Dictionary Saved",
            f"Custom dictionary saved with {len(replacements)} entries."
        )
        self.accept()
