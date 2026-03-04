"""
Changelog dialog shown before downloading an auto-update.
Displays the GitHub release notes so the user can review what changed.
"""

from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextBrowser
from PySide6.QtCore import Qt

from gui.theme import RoundedDialog, BG_SURFACE, BORDER, TEXT_PRIMARY


class ChangelogDialog(RoundedDialog):
    """Shows release notes for a pending update with Cancel / Proceed buttons."""

    def __init__(self, version_str, release_body="", parent=None):
        super().__init__(parent)
        self._accepted = False

        self.setWindowTitle(f"Resonance {version_str} \u2014 What's New")
        self.setFixedWidth(520)
        self.setMinimumHeight(340)
        self.setMaximumHeight(600)

        layout = QVBoxLayout()
        layout.setSpacing(12)

        # Version header
        header = QLabel(f"Version {version_str}")
        header.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {TEXT_PRIMARY};")
        layout.addWidget(header)

        # Release notes browser
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setStyleSheet(
            f"QTextBrowser {{"
            f"  background-color: {BG_SURFACE};"
            f"  border: 1px solid {BORDER};"
            f"  border-radius: 6px;"
            f"  padding: 8px;"
            f"  color: {TEXT_PRIMARY};"
            f"  font-size: 12px;"
            f"}}"
        )

        body = release_body.strip() if release_body else ""
        if body:
            browser.setMarkdown(body)
        else:
            browser.setPlainText("No release notes available.")

        layout.addWidget(browser, 1)  # stretch factor 1 so it fills space

        # Button row
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedWidth(100)
        cancel_btn.setStyleSheet(
            f"QPushButton {{ background-color: {BG_SURFACE}; color: {TEXT_PRIMARY};"
            f" border: 1px solid {BORDER}; border-radius: 4px; padding: 6px 14px;"
            f" font-size: 12px; font-weight: bold; }}"
            f"QPushButton:hover {{ background-color: {BORDER}; }}"
        )
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        proceed_btn = QPushButton("Proceed with Update")
        proceed_btn.setFixedWidth(160)
        proceed_btn.setStyleSheet(
            "QPushButton { background-color: #2ecc71; color: #fff;"
            " border: none; border-radius: 4px; padding: 6px 14px;"
            " font-size: 12px; font-weight: bold; }"
            "QPushButton:hover { background-color: #27ae60; }"
        )
        proceed_btn.clicked.connect(self._on_proceed)
        btn_layout.addWidget(proceed_btn)

        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def _on_proceed(self):
        self._accepted = True
        self.accept()

    def was_accepted(self):
        """Return True if the user clicked 'Proceed with Update'."""
        return self._accepted
