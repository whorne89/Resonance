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
    BASE_HEIGHT = 80
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
        self.setFixedSize(self.WIDTH, self.BASE_HEIGHT)

        self._message = ""
        self._details = ""
        self._height = self.BASE_HEIGHT
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
            y = geom.y() + geom.height() - self._height - self.MARGIN
            self.move(x, y)

    # --- Public API ---

    def show_toast(self, message, details=""):
        """Show a toast with the given message and optional bold details below.

        Args:
            message: Main message text
            details: Optional bold text shown below the message
        """
        self._message = message
        self._details = details

        # Calculate height based on content
        from PySide6.QtGui import QFontMetrics
        body_font = QFont()
        body_font.setPixelSize(13)
        fm = QFontMetrics(body_font)
        content_x = 16
        max_width = self.WIDTH - content_x - 16

        msg_rect = fm.boundingRect(
            0, 0, max_width, 999,
            Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap,
            message,
        )
        total_body = msg_rect.height()

        if details:
            bold_font = QFont()
            bold_font.setPixelSize(13)
            bold_font.setBold(True)
            bfm = QFontMetrics(bold_font)
            det_rect = bfm.boundingRect(
                0, 0, max_width, 999,
                Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap,
                details,
            )
            total_body += 4 + det_rect.height()  # 4px gap between message and details

        # header takes ~44px, body needs total_body, plus 12px bottom padding
        self._height = max(self.BASE_HEIGHT, 44 + total_body + 12)
        self.setFixedSize(self.WIDTH, self._height)

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
        h = self._height
        path = QPainterPath()
        path.addRoundedRect(
            0.5, 0.5,
            self.WIDTH - 1, h - 1,
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
        painter.drawRoundedRect(0, 0, 3, h, 1, 1)
        painter.setClipping(False)

        # Header: icon + "Resonance"
        header_y = 22
        content_x = 16

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
        from PySide6.QtGui import QFontMetrics

        body_font = QFont()
        body_font.setPixelSize(12)
        painter.setFont(body_font)
        painter.setPen(QColor(255, 255, 255, 190))

        max_width = self.WIDTH - content_x - 16
        body_top = header_y + 14
        msg_rect = QRect(content_x, body_top, max_width, self._height - body_top)
        painter.drawText(msg_rect, Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap, self._message)

        # Bold details below message
        if self._details:
            fm = QFontMetrics(body_font)
            msg_bound = fm.boundingRect(
                0, 0, max_width, 999,
                Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap,
                self._message,
            )
            det_top = body_top + msg_bound.height() + 4

            bold_font = QFont()
            bold_font.setPixelSize(13)
            bold_font.setBold(True)
            painter.setFont(bold_font)
            painter.setPen(QColor(255, 255, 255, 230))

            det_rect = QRect(content_x, det_top, max_width, self._height - det_top)
            painter.drawText(det_rect, Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap, self._details)

        painter.end()


class DownloadToast(ToastNotification):
    """
    Toast notification with an animated marquee progress bar at the bottom.

    Used during model downloads to show indeterminate progress.
    """

    MARQUEE_HEIGHT = 3
    MARQUEE_WIDTH_RATIO = 0.30  # Highlight is 30% of toast width
    MARQUEE_CYCLE_MS = 1500     # Full cycle in milliseconds
    TICK_MS = 30                # Animation frame interval

    def __init__(self, parent=None):
        super().__init__(parent)
        self._downloading = False
        self._marquee_pos = 0.0  # 0.0 to 1.0

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(self.TICK_MS)
        self._anim_timer.timeout.connect(self._tick_marquee)

    def show_download(self, message):
        """Show the toast with a marquee progress bar. Does NOT auto-dismiss."""
        self._downloading = True
        self._marquee_pos = 0.0
        self.show_toast(message)
        self._anim_timer.start()

    def _start_hold(self):
        """Override: skip auto-dismiss timer while downloading."""
        if not self._downloading:
            super()._start_hold()

    def _tick_marquee(self):
        """Advance marquee position and repaint."""
        step = self.TICK_MS / self.MARQUEE_CYCLE_MS
        self._marquee_pos = (self._marquee_pos + step) % 1.0
        self.update()

    def set_complete(self, message):
        """Stop animation, update text, and auto-dismiss after 2 seconds."""
        self._downloading = False
        self._anim_timer.stop()
        self._message = message
        self.update()
        self._hold_timer.start(2000)

    def paintEvent(self, event):
        """Draw the toast then overlay a marquee bar at the bottom."""
        super().paintEvent(event)

        if not self._downloading:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Clip to the rounded toast shape so the bar doesn't leak outside
        clip = QPainterPath()
        clip.addRoundedRect(
            0.5, 0.5,
            self.WIDTH - 1, self._height - 1,
            self.RADIUS, self.RADIUS,
        )
        painter.setClipPath(clip)

        # Marquee bar at the very bottom
        bar_y = self._height - self.MARQUEE_HEIGHT
        highlight_w = int(self.WIDTH * self.MARQUEE_WIDTH_RATIO)

        # Position slides from -highlight_w to WIDTH
        total_travel = self.WIDTH + highlight_w
        x = int(self._marquee_pos * total_travel) - highlight_w

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self.ACCENT_COLOR))
        painter.drawRect(x, bar_y, highlight_w, self.MARQUEE_HEIGHT)

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

        self._text = "Text entered"
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

    def show_toast(self, text="Text entered"):
        """Show a brief indicator with the given text."""
        self._text = text
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
            self._text,
        )
        painter.end()
