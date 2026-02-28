"""
Toast notification overlay for Resonance.
Auto-dismissing dark pill toast positioned at the bottom-right of the screen.
"""

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QPainterPath, QFont, QPixmap, QGuiApplication
from pathlib import Path

from utils.resource_path import get_resource_path


class ToastNotification(QWidget):
    """
    Frameless, transparent, always-on-top toast notification.

    Shows a dark pill with app icon, title, and message text.
    Auto-dismisses after 3 seconds with fade animation.
    """

    # Dimensions
    WIDTH = 320
    HEIGHT = 80
    RADIUS = 12
    MARGIN = 20  # Distance from screen edges

    # Colors (matching RecordingOverlay)
    BG_COLOR = QColor(26, 26, 46, 217)       # #1a1a2e at ~85% opacity
    BORDER_COLOR = QColor(45, 45, 78, 128)    # #2d2d4e at 50%
    ACCENT_COLOR = QColor(52, 152, 219)       # #3498db blue

    # Timing
    HOLD_MS = 3000
    FADE_IN_MS = 200
    FADE_OUT_MS = 300

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.WIDTH, self.HEIGHT)

        self._message = ""
        self._icon_pixmap = None
        self._fade_anim = None
        self._hold_timer = QTimer(self)
        self._hold_timer.setSingleShot(True)
        self._hold_timer.timeout.connect(self._fade_out)

        # Load tray icon for display in toast
        self._load_icon()

    def _load_icon(self):
        """Load the tray idle icon for display in the toast header."""
        icon_path = Path(get_resource_path("icons")) / "tray_idle.png"
        if icon_path.exists():
            pm = QPixmap(str(icon_path))
            if not pm.isNull():
                self._icon_pixmap = pm.scaled(
                    16, 16,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )

    def _position_on_screen(self):
        """Position the toast at the bottom-right of the primary screen."""
        screen = QGuiApplication.primaryScreen()
        if screen:
            geom = screen.availableGeometry()
            x = geom.x() + geom.width() - self.WIDTH - self.MARGIN
            y = geom.y() + geom.height() - self.HEIGHT - self.MARGIN
            self.move(x, y)

    # --- Public API ---

    def show_toast(self, message):
        """Show a toast with the given message. Replaces any active toast."""
        self._message = message

        # Stop any running animations/timers
        self._stop_fade()
        self._hold_timer.stop()

        # Position and show
        self._position_on_screen()
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        self.update()

        # Fade in
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(self.FADE_IN_MS)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._fade_anim.finished.connect(self._start_hold)
        self._fade_anim.start()

    # --- Animation ---

    def _start_hold(self):
        """Start the hold timer after fade-in completes."""
        self._hold_timer.start(self.HOLD_MS)

    def _fade_out(self):
        """Animate fade out, then hide."""
        self._stop_fade()
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(self.FADE_OUT_MS)
        self._fade_anim.setStartValue(self.windowOpacity())
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._fade_anim.finished.connect(self.hide)
        self._fade_anim.start()

    def _stop_fade(self):
        """Stop any running fade animation."""
        if self._fade_anim is not None:
            self._fade_anim.stop()
            self._fade_anim = None

    # --- Painting ---

    def paintEvent(self, event):
        """Draw the toast notification."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Clipping path for rounded rectangle
        path = QPainterPath()
        path.addRoundedRect(
            0.5, 0.5,
            self.WIDTH - 1, self.HEIGHT - 1,
            self.RADIUS, self.RADIUS,
        )

        # Background + border
        painter.setPen(QPen(self.BORDER_COLOR, 1))
        painter.setBrush(QBrush(self.BG_COLOR))
        painter.drawPath(path)

        # Left accent line
        painter.setClipPath(path)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self.ACCENT_COLOR))
        painter.drawRoundedRect(0, 0, 3, self.HEIGHT, 1, 1)
        painter.setClipping(False)

        # Header: icon + "Resonance"
        header_y = 20
        content_x = 16

        if self._icon_pixmap:
            painter.drawPixmap(content_x, header_y - 12, self._icon_pixmap)
            text_x = content_x + 22
        else:
            text_x = content_x

        title_font = QFont()
        title_font.setPixelSize(11)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor(255, 255, 255, 180))
        painter.drawText(text_x, header_y, "Resonance")

        # Message body
        body_font = QFont()
        body_font.setPixelSize(13)
        painter.setFont(body_font)
        painter.setPen(QColor(255, 255, 255, 204))  # ~80% opacity

        # Draw message with elision if too long
        from PySide6.QtGui import QFontMetrics
        fm = QFontMetrics(body_font)
        max_width = self.WIDTH - content_x - 16
        elided = fm.elidedText(self._message, Qt.TextElideMode.ElideRight, max_width)
        painter.drawText(content_x, header_y + 24, elided)

        painter.end()


class ClipboardToast(QWidget):
    """
    Small floating 'Copied to clipboard' indicator.

    Centered at bottom of screen, auto-dismisses after ~1 second
    with fade in/out animation.  Same dark styling as ToastNotification.
    """

    WIDTH = 190
    HEIGHT = 36
    RADIUS = 18
    MARGIN = 60  # Distance from bottom of screen

    BG_COLOR = QColor(26, 26, 46, 230)       # #1a1a2e at ~90% opacity
    BORDER_COLOR = QColor(45, 45, 78, 140)    # #2d2d4e
    TEXT_COLOR = QColor(255, 255, 255, 210)

    FADE_IN_MS = 120
    HOLD_MS = 600
    FADE_OUT_MS = 280

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.WIDTH, self.HEIGHT)

        self._fade_anim = None
        self._hold_timer = QTimer(self)
        self._hold_timer.setSingleShot(True)
        self._hold_timer.timeout.connect(self._fade_out)

    def _position_on_screen(self):
        """Center the toast horizontally near the bottom of the screen."""
        screen = QGuiApplication.primaryScreen()
        if screen:
            geom = screen.availableGeometry()
            x = geom.x() + (geom.width() - self.WIDTH) // 2
            y = geom.y() + geom.height() - self.HEIGHT - self.MARGIN
            self.move(x, y)

    def show_toast(self):
        """Show the 'Copied to clipboard' indicator."""
        self._stop_fade()
        self._hold_timer.stop()

        self._position_on_screen()
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        self.update()

        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(self.FADE_IN_MS)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._fade_anim.finished.connect(self._start_hold)
        self._fade_anim.start()

    def _start_hold(self):
        self._hold_timer.start(self.HOLD_MS)

    def _fade_out(self):
        self._stop_fade()
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(self.FADE_OUT_MS)
        self._fade_anim.setStartValue(self.windowOpacity())
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._fade_anim.finished.connect(self.hide)
        self._fade_anim.start()

    def _stop_fade(self):
        if self._fade_anim is not None:
            self._fade_anim.stop()
            self._fade_anim = None

    def paintEvent(self, event):
        """Draw the small pill indicator."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(
            0.5, 0.5,
            self.WIDTH - 1, self.HEIGHT - 1,
            self.RADIUS, self.RADIUS,
        )

        painter.setPen(QPen(self.BORDER_COLOR, 1))
        painter.setBrush(QBrush(self.BG_COLOR))
        painter.drawPath(path)

        font = QFont("Calibri", 0)
        font.setPixelSize(12)
        painter.setFont(font)
        painter.setPen(self.TEXT_COLOR)
        painter.drawText(
            0, 0, self.WIDTH, self.HEIGHT,
            Qt.AlignmentFlag.AlignCenter,
            "Copied to clipboard",
        )
        painter.end()
