"""
Interactive update toast notification for Resonance.
Shows a Yes/No prompt when a new version is available.
"""

from pathlib import Path

from PySide6.QtWidgets import QWidget, QPushButton, QHBoxLayout
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QPainterPath, QFont, QPixmap, QGuiApplication

from utils.resource_path import get_resource_path


class UpdateToast(QWidget):
    """
    Interactive toast notification for update prompts.

    Same visual style as ToastNotification (dark pill, bottom-right, accent bar,
    "Resonance" header) but with clickable Yes/No buttons instead of
    WindowTransparentForInput.

    Auto-dismisses after 10 seconds if user doesn't interact.
    """

    accepted = Signal()
    dismissed = Signal()

    # Dimensions
    WIDTH = 340
    HEIGHT = 140
    RADIUS = 12
    MARGIN = 20

    # Colors (matching ToastNotification)
    BG_COLOR = QColor(26, 26, 46, 230)
    BORDER_COLOR = QColor(45, 45, 78, 128)
    ACCENT_COLOR = QColor(52, 152, 219)

    # Timing
    AUTO_DISMISS_MS = 25000
    FADE_IN_MS = 200
    FADE_OUT_MS = 300

    def __init__(self, version_str, parent=None):
        super().__init__(parent)

        self._version = version_str
        self._message = (
            f"Resonance {version_str} is available\n"
            "The app will close and restart to update."
        )

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.WIDTH, self.HEIGHT)

        # Load icon
        self._icon_pixmap = None
        icon_path = Path(get_resource_path("icons")) / "tray_idle.png"
        if icon_path.exists():
            pm = QPixmap(str(icon_path))
            if not pm.isNull():
                self._icon_pixmap = pm.scaled(
                    16, 16,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )

        # Buttons
        self._yes_btn = QPushButton("Yes", self)
        self._yes_btn.setFixedSize(60, 28)
        self._yes_btn.setStyleSheet(
            "QPushButton { background-color: #2ecc71; color: #fff; border: none;"
            " border-radius: 4px; font-size: 12px; font-weight: bold; }"
            "QPushButton:hover { background-color: #27ae60; }"
        )
        self._yes_btn.clicked.connect(self._on_accept)

        self._no_btn = QPushButton("No", self)
        self._no_btn.setFixedSize(60, 28)
        self._no_btn.setStyleSheet(
            "QPushButton { background-color: #3d3d5c; color: rgba(255,255,255,180); border: none;"
            " border-radius: 4px; font-size: 12px; font-weight: bold; }"
            "QPushButton:hover { background-color: #4d4d6c; }"
        )
        self._no_btn.clicked.connect(self._on_dismiss)

        # Position buttons at the bottom-right of the toast
        btn_y = self.HEIGHT - 38
        self._no_btn.move(self.WIDTH - 16 - 60, btn_y)
        self._yes_btn.move(self.WIDTH - 16 - 60 - 8 - 60, btn_y)

        # Animation
        self._fade_anim = None

        # Auto-dismiss timer
        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self._on_dismiss)

    def show_toast(self):
        """Show the update toast with fade-in and start auto-dismiss timer."""
        self._position_on_screen()
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()

        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(self.FADE_IN_MS)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._fade_anim.finished.connect(lambda: self._dismiss_timer.start(self.AUTO_DISMISS_MS))
        self._fade_anim.start()

    def _position_on_screen(self):
        """Position at bottom-right of primary screen."""
        screen = QGuiApplication.primaryScreen()
        if screen:
            geom = screen.availableGeometry()
            x = geom.x() + geom.width() - self.WIDTH - self.MARGIN
            y = geom.y() + geom.height() - self.HEIGHT - self.MARGIN
            self.move(x, y)

    def _on_accept(self):
        self._dismiss_timer.stop()
        self._fade_out(self.accepted)

    def _on_dismiss(self):
        self._dismiss_timer.stop()
        self._fade_out(self.dismissed)

    def _fade_out(self, signal_to_emit):
        """Fade out then emit the given signal."""
        if self._fade_anim is not None:
            self._fade_anim.stop()

        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(self.FADE_OUT_MS)
        self._fade_anim.setStartValue(self.windowOpacity())
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._fade_anim.finished.connect(self.hide)
        self._fade_anim.finished.connect(signal_to_emit.emit)
        self._fade_anim.start()

    def paintEvent(self, event):
        """Draw the toast background, accent bar, header, and message."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Rounded rectangle
        path = QPainterPath()
        path.addRoundedRect(
            0.5, 0.5,
            self.WIDTH - 1, self.HEIGHT - 1,
            self.RADIUS, self.RADIUS,
        )

        painter.setPen(QPen(self.BORDER_COLOR, 1))
        painter.setBrush(QBrush(self.BG_COLOR))
        painter.drawPath(path)

        # Left accent bar
        painter.setClipPath(path)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self.ACCENT_COLOR))
        painter.drawRoundedRect(0, 0, 3, self.HEIGHT, 1, 1)
        painter.setClipping(False)

        # Header: icon + "Resonance"
        content_x = 16
        header_y = 22

        if self._icon_pixmap:
            painter.drawPixmap(content_x, header_y - 13, self._icon_pixmap)
            text_x = content_x + 22
        else:
            text_x = content_x

        title_font = QFont()
        title_font.setPixelSize(15)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor(255, 255, 255, 220))
        painter.drawText(text_x, header_y, "Resonance")

        # Message body
        from PySide6.QtCore import QRect
        body_font = QFont()
        body_font.setPixelSize(12)
        painter.setFont(body_font)
        painter.setPen(QColor(255, 255, 255, 190))

        max_width = self.WIDTH - content_x - 16
        body_top = header_y + 14
        body_bottom = self.HEIGHT - 46  # Leave room for buttons
        msg_rect = QRect(content_x, body_top, max_width, body_bottom - body_top)
        painter.drawText(msg_rect, Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap, self._message)

        painter.end()
