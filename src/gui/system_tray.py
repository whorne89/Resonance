"""
System tray interface for Resonance.
Provides minimal UI with icon and context menu.
"""

from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QMessageBox, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PySide6.QtGui import QIcon, QAction
from PySide6.QtCore import Signal, QObject, Qt
from pathlib import Path

from utils.resource_path import get_resource_path
from gui.toast_notification import ToastNotification
from gui.theme import RoundedDialog


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

        # Toast notification overlay
        self._toast = ToastNotification()

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

    def showMessage(self, *args, **kwargs):
        """Override Qt native notification — redirect to custom toast.

        Prevents Windows from showing its own balloon/toast notification.
        Accepts both the Qt signature and our custom keyword args.
        """
        # Extract message: positional (title, message, ...) or keyword
        if len(args) >= 2:
            self._toast.show_toast(args[1])
        elif len(args) >= 1:
            self._toast.show_toast(args[0])

    def show_message(self, title, message, icon_type=QSystemTrayIcon.MessageIcon.Information, duration=3000):
        """
        Show a toast notification overlay.

        Args:
            title: Notification title (unused — toast always shows "Resonance")
            message: Notification message
            icon_type: Icon type (unused — kept for API compatibility)
            duration: Duration in milliseconds (unused — toast auto-dismisses)
        """
        self._toast.show_toast(message)

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
        Show error notification via toast overlay.

        Args:
            error_message: Error message to display
        """
        self._toast.show_toast(error_message)

    def show_about(self):
        """Show about dialog window."""
        dialog = AboutDialog()
        dialog.exec()


class AboutDialog(RoundedDialog):
    """Custom rounded About dialog for Resonance."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About Resonance")
        self.setFixedWidth(380)

        from importlib.metadata import version as pkg_version, PackageNotFoundError
        try:
            app_version = pkg_version("resonance")
        except PackageNotFoundError:
            app_version = "dev"

        layout = QVBoxLayout()
        layout.setSpacing(12)

        title = QLabel("Resonance")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        desc = QLabel(
            "Voice-to-text powered by local Whisper AI.\n\n"
            "Hold your hotkey while speaking, then release\n"
            "to transcribe. No internet required \u2014\n"
            "completely private and secure."
        )
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet("color: rgba(255, 255, 255, 180);")
        layout.addWidget(desc)

        author = QLabel("Created by William Horne")
        author.setAlignment(Qt.AlignmentFlag.AlignCenter)
        author.setStyleSheet("color: rgba(255, 255, 255, 140);")
        layout.addWidget(author)

        version = QLabel(f"Version {app_version}")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version.setStyleSheet("color: rgba(255, 255, 255, 140);")
        layout.addWidget(version)

        layout.addSpacing(4)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.setFixedWidth(80)
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.setLayout(layout)
