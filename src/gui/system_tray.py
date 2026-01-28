"""
System tray interface for Resonance.
Provides minimal UI with icon and context menu.
"""

from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QMessageBox
from PySide6.QtGui import QIcon, QAction
from PySide6.QtCore import Signal, QObject
from pathlib import Path

from utils.resource_path import get_resource_path


class SystemTrayIcon(QSystemTrayIcon):
    """System tray icon with context menu and status updates."""

    # Signals
    settings_requested = Signal()
    quit_requested = Signal()

    def __init__(self, hotkey_display="Ctrl+Alt+R", parent=None):
        """
        Initialize system tray icon.

        Args:
            hotkey_display: Formatted hotkey string for display
            parent: Parent QObject
        """
        super().__init__(parent)

        self.hotkey_display = hotkey_display

        # Load icons - use resource path utility for bundled EXE support
        self.icon_dir = Path(get_resource_path("icons"))
        self.load_icons()

        # Set initial state
        self.set_idle_state()
        self.setToolTip("Resonance - Voice to Text")

        # Create context menu
        self.create_menu()

        # Connect signals
        self.activated.connect(self.on_tray_activated)

        # Show the icon
        self.show()

    def load_icons(self):
        """Load or create tray icons."""
        from PySide6.QtGui import QPixmap, QPainter, QColor
        from PySide6.QtCore import Qt

        icon_idle_path = self.icon_dir / "tray_idle.png"
        icon_recording_path = self.icon_dir / "tray_recording.png"

        # Try to load icons from files
        if icon_idle_path.exists() and icon_idle_path.stat().st_size > 0:
            self.icon_idle = QIcon(str(icon_idle_path))
            if self.icon_idle.isNull():
                self.icon_idle = self.create_simple_icon(QColor(128, 128, 128))  # Gray
        else:
            # Create simple gray icon
            self.icon_idle = self.create_simple_icon(QColor(128, 128, 128))

        if icon_recording_path.exists() and icon_recording_path.stat().st_size > 0:
            self.icon_recording = QIcon(str(icon_recording_path))
            if self.icon_recording.isNull():
                self.icon_recording = self.create_simple_icon(QColor(255, 0, 0))  # Red
        else:
            # Create simple red icon
            self.icon_recording = self.create_simple_icon(QColor(255, 0, 0))

    def create_simple_icon(self, color):
        """
        Create a simple colored icon programmatically.

        Args:
            color: QColor for the icon

        Returns:
            QIcon with simple colored circle
        """
        from PySide6.QtGui import QPixmap, QPainter, QColor
        from PySide6.QtCore import Qt

        # Create a 32x32 pixmap
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)

        # Draw on it
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw a circle
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(4, 4, 24, 24)

        painter.end()

        return QIcon(pixmap)

    def create_menu(self):
        """Create context menu for system tray."""
        menu = QMenu()

        # Settings action
        self.action_settings = QAction("Settings", self)
        self.action_settings.triggered.connect(self.settings_requested.emit)
        menu.addAction(self.action_settings)

        menu.addSeparator()

        # About action
        self.action_about = QAction("About", self)
        self.action_about.triggered.connect(self.show_about)
        menu.addAction(self.action_about)

        menu.addSeparator()

        # Exit action
        self.action_exit = QAction("Exit", self)
        self.action_exit.triggered.connect(self.quit_requested.emit)
        menu.addAction(self.action_exit)

        self.setContextMenu(menu)

    def on_tray_activated(self, reason):
        """
        Handle tray icon activation.

        Args:
            reason: Activation reason (click, double-click, etc.)
        """
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            # Double-click opens settings
            self.settings_requested.emit()

    def set_idle_state(self):
        """Set icon to idle state."""
        self.setIcon(self.icon_idle)
        self.setToolTip(f"Resonance - Ready ({self.hotkey_display})")

    def set_recording_state(self):
        """Set icon to recording state."""
        self.setIcon(self.icon_recording)
        self.setToolTip("Resonance - Recording...")

    def set_transcribing_state(self):
        """Set icon to transcribing state."""
        # Use recording icon with different tooltip
        self.setIcon(self.icon_recording)
        self.setToolTip("Resonance - Transcribing...")

    def show_message(self, title, message, icon_type=QSystemTrayIcon.MessageIcon.Information, duration=3000):
        """
        Show a system tray notification.

        Args:
            title: Notification title
            message: Notification message
            icon_type: Icon type (Information, Warning, Critical)
            duration: Duration in milliseconds
        """
        self.showMessage(title, message, icon_type, duration)

    def show_about(self):
        """Show about dialog window."""
        about_text = (
            "Resonance - Voice to Text Application\n\n"
            "Resonance is a voice-to-text application that is toggled\n"
            "by using a configurable hotkey. Hold the hotkey while\n"
            "speaking, then release to transcribe your speech into text.\n\n"
            "Uses local Whisper AI - no internet required,\n"
            "completely private and secure.\n\n"
            "Created by William Horne\n\n"
            "Version 1.1.1"
        )

        # Create and show About dialog
        msg_box = QMessageBox()
        msg_box.setWindowTitle("About Resonance")
        msg_box.setText(about_text)
        msg_box.setIcon(QMessageBox.Icon.Information)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.exec()

    def show_transcription_complete(self, text):
        """
        Show notification that transcription is complete.

        Args:
            text: Transcribed text (truncated for notification)
        """
        # Truncate text for notification
        preview = text[:50] + "..." if len(text) > 50 else text
        self.show_message(
            "Transcription Complete",
            f"Typed: {preview}",
            QSystemTrayIcon.MessageIcon.Information,
            2000
        )

    def show_error(self, error_message):
        """
        Show error notification.

        Args:
            error_message: Error message to display
        """
        self.show_message(
            "Error",
            error_message,
            QSystemTrayIcon.MessageIcon.Critical,
            5000
        )
