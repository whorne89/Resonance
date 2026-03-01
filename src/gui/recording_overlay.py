"""
Recording overlay for Resonance.
Floating pill-shaped widget showing recording/processing state with live waveform.
"""

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QTimer, QRect, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QPainterPath, QFont, QFontMetrics, QGuiApplication


class RecordingOverlay(QWidget):
    """
    Frameless, transparent, always-on-top pill overlay.

    States:
    - Hidden: not visible
    - Recording: red dot (pulsing) + live waveform bars
    - Processing: blue animated dots
    """

    # Constants
    PILL_WIDTH = 200
    PILL_HEIGHT = 44
    PILL_RADIUS = 22
    BOTTOM_MARGIN = 60
    BAR_COUNT = 7
    WAVEFORM_UPDATE_MS = 50
    BADGE_HEIGHT = 22
    BADGE_GAP = 4
    BADGE_SPACING = 3  # Gap between stacked badges

    # Colors
    BG_COLOR = QColor(26, 26, 46, 217)       # #1a1a2e at ~85% opacity
    BORDER_COLOR = QColor(45, 45, 78, 128)    # #2d2d4e at 50%
    REC_COLOR = QColor(231, 76, 60)           # #e74c3c red
    PROC_COLOR = QColor(52, 152, 219)         # #3498db blue
    TYPE_COLOR = QColor(46, 204, 113)         # #2ecc71 green
    ERROR_COLOR = QColor(231, 76, 60)         # #e74c3c red

    def __init__(self, parent=None):
        super().__init__(parent)

        # State
        self._state = "hidden"  # "hidden", "recording", "processing", "typing"
        self._bar_heights = [0.0] * self.BAR_COUNT
        self._target_heights = [0.0] * self.BAR_COUNT
        self._dot_opacity = 1.0
        self._dot_direction = -1  # -1 = dimming, +1 = brightening
        self._proc_dot_index = 0
        self._proc_tick = 0
        self._typing_tick = 0
        self._typing_dot_count = 0  # 0-3 for animated "..."
        self._typing_text = "Typing"
        self._typing_show_dots = True
        self._typing_color = self.TYPE_COLOR

        # Audio source (set by caller)
        self._audio_recorder = None

        # Feature badges (e.g. ["Post-processing", "OCR"])
        self._features = []

        # Accuracy badge (shown during typing/pasted state)
        self._accuracy = None  # 0.0-1.0 or None
        self._detected_app = None  # e.g. "chat", "email", "code"

        # Window setup
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.PILL_WIDTH, self.PILL_HEIGHT)

        # Position at bottom center of primary screen
        self._position_on_screen()

        # Animation timer (drives waveform + dot pulse)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

        # Fade animation
        self._fade_anim = None

    def set_audio_recorder(self, recorder):
        """Set the audio recorder to read RMS levels from."""
        self._audio_recorder = recorder

    def set_features(self, features):
        """Set active feature labels shown as a badge above the pill.

        Args:
            features: list of feature names, e.g. ["Post-processing"]
        """
        self._features = list(features)

    def set_accuracy(self, confidence):
        """Set transcription accuracy for badge display during typing state.

        Args:
            confidence: 0.0-1.0 confidence score, or None to hide.
        """
        self._accuracy = confidence

    def set_detected_app(self, app_type):
        """Set the detected app type for badge display during typing state.

        Args:
            app_type: App type string (e.g. "chat", "email") or None to hide.
        """
        self._detected_app = app_type

    def _active_badges(self):
        """Return the list of badge labels for the current state."""
        if self._state == "typing":
            badges = []
            if self._detected_app and self._detected_app != "general":
                badges.append(self._detected_app.capitalize())
            if self._accuracy is not None:
                badges.append(f"Estimated Accuracy: {self._accuracy:.0%}")
            return badges
        if self._features:
            return self._features
        return []

    def _total_height(self):
        """Total widget height including badge area if badges are active."""
        n = len(self._active_badges())
        if n:
            badges = n * self.BADGE_HEIGHT + (n - 1) * self.BADGE_SPACING + self.BADGE_GAP
            return self.PILL_HEIGHT + badges
        return self.PILL_HEIGHT

    def _position_on_screen(self):
        """Position the overlay at bottom-center of the primary screen."""
        h = self._total_height()
        self.setFixedSize(self.PILL_WIDTH, h)
        screen = QGuiApplication.primaryScreen()
        if screen:
            geom = screen.availableGeometry()
            x = geom.x() + (geom.width() - self.PILL_WIDTH) // 2
            y = geom.y() + geom.height() - h - self.BOTTOM_MARGIN
            self.move(x, y)

    # --- Public API ---

    def show_recording(self):
        """Show overlay in recording state."""
        self._position_on_screen()
        self._state = "recording"
        self._bar_heights = [0.0] * self.BAR_COUNT
        self._target_heights = [0.0] * self.BAR_COUNT
        self._dot_opacity = 1.0
        self._dot_direction = -1
        self._stop_fade()
        self.setWindowOpacity(1.0)
        self.show()
        self.raise_()
        self._timer.start(self.WAVEFORM_UPDATE_MS)

    def show_processing(self):
        """Transition to processing state."""
        self._state = "processing"
        self._bar_heights = [0.0] * self.BAR_COUNT
        self._proc_dot_index = 0
        self._proc_tick = 0
        self.update()

    def show_typing(self):
        """Transition to typing state (char-by-char output with animated dots)."""
        self._state = "typing"
        self._typing_text = "Typing"
        self._typing_show_dots = True
        self._typing_color = self.TYPE_COLOR
        self._typing_tick = 0
        self._position_on_screen()
        self.update()

    def show_pasted(self):
        """Transition to pasted state (clipboard output)."""
        self._state = "typing"
        self._typing_text = "Text Entered"
        self._typing_show_dots = False
        self._typing_color = self.TYPE_COLOR
        self._position_on_screen()
        self.update()

    def show_complete(self):
        """Show 'Complete' after typing finishes."""
        self._typing_text = "Complete"
        self._typing_show_dots = False
        self._typing_color = self.TYPE_COLOR
        self.update()

    def show_no_speech(self):
        """Show 'No speech detected' in red."""
        self._state = "typing"
        self._typing_text = "No speech detected"
        self._typing_show_dots = False
        self._typing_color = self.ERROR_COLOR
        self.update()

    def hide_overlay(self, delay_ms=0):
        """Fade out and hide the overlay after an optional delay."""
        if delay_ms > 0:
            QTimer.singleShot(delay_ms, self._begin_hide)
        else:
            self._begin_hide()

    def _begin_hide(self):
        """Stop animations and fade out."""
        self._timer.stop()
        self._state = "hidden"
        self._fade_out()

    # --- Animation ---

    def _tick(self):
        """Called every WAVEFORM_UPDATE_MS to update animations."""
        if self._state == "recording":
            self._update_waveform()
            self._update_dot_pulse()
        elif self._state == "processing":
            self._proc_tick += 1
            if self._proc_tick % 4 == 0:  # Every ~200ms
                self._proc_dot_index = (self._proc_dot_index + 1) % 3
        elif self._state == "typing":
            self._typing_tick += 1
            if self._typing_tick % 6 == 0:  # Every ~300ms — cycle dots
                self._typing_dot_count = (self._typing_dot_count + 1) % 4
        self.update()

    def _update_waveform(self):
        """Update waveform bar heights from live audio RMS."""
        rms = 0.0
        if self._audio_recorder is not None:
            rms = self._audio_recorder.current_rms

        # Scale RMS to 0-1 range (calibrated for normal speech levels).
        # Settings dialog uses rms * 3500 for 0-100 scale; this is equivalent
        # tuning so normal speech produces ~30-70% bar height.
        level = min(1.0, rms * 50.0)

        # Shift bars left, add new level on the right
        self._target_heights = self._target_heights[1:] + [level]

        # Smooth interpolation toward targets
        for i in range(self.BAR_COUNT):
            diff = self._target_heights[i] - self._bar_heights[i]
            self._bar_heights[i] += diff * 0.4

    def _update_dot_pulse(self):
        """Pulse the recording dot opacity."""
        self._dot_opacity += self._dot_direction * 0.04
        if self._dot_opacity <= 0.4:
            self._dot_opacity = 0.4
            self._dot_direction = 1
        elif self._dot_opacity >= 1.0:
            self._dot_opacity = 1.0
            self._dot_direction = -1

    def _fade_out(self):
        """Animate fade out."""
        self._stop_fade()
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(300)
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
        """Draw the pill overlay."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Offset: pill is drawn at the bottom of the widget
        pill_y = self._total_height() - self.PILL_HEIGHT

        # Draw badge(s) above the pill (features during recording, accuracy during typing)
        if self._active_badges():
            self._paint_badge(painter)

        # Draw pill background
        painter.save()
        painter.translate(0, pill_y)

        path = QPainterPath()
        path.addRoundedRect(
            0.5, 0.5,
            self.PILL_WIDTH - 1, self.PILL_HEIGHT - 1,
            self.PILL_RADIUS, self.PILL_RADIUS
        )

        painter.setPen(QPen(self.BORDER_COLOR, 1))
        painter.setBrush(QBrush(self.BG_COLOR))
        painter.drawPath(path)

        if self._state == "recording":
            self._paint_recording(painter)
        elif self._state == "processing":
            self._paint_processing(painter)
        elif self._state == "typing":
            self._paint_typing(painter)

        painter.restore()
        painter.end()

    def _paint_badge(self, painter):
        """Draw stacked feature badges centered above the main pill."""
        font = QFont()
        font.setPixelSize(12)
        fm = QFontMetrics(font)
        painter.setFont(font)

        for i, label in enumerate(self._active_badges()):
            y = i * (self.BADGE_HEIGHT + self.BADGE_SPACING)
            text_width = fm.horizontalAdvance(label)
            badge_w = int(text_width + 18)
            badge_r = self.BADGE_HEIGHT // 2
            badge_x = (self.PILL_WIDTH - badge_w) / 2

            path = QPainterPath()
            path.addRoundedRect(badge_x, y + 0.5, badge_w, self.BADGE_HEIGHT - 1, badge_r, badge_r)

            painter.setPen(QPen(self.BORDER_COLOR, 1))
            painter.setBrush(QBrush(QColor(26, 26, 46, 200)))
            painter.drawPath(path)

            painter.setPen(QColor(255, 255, 255, 160))
            painter.drawText(
                int(badge_x), y, badge_w, self.BADGE_HEIGHT,
                Qt.AlignmentFlag.AlignCenter,
                label,
            )

    def _paint_recording(self, painter):
        """Draw recording indicator: pulsing red dot + waveform bars."""
        # Pulsing red dot
        dot_color = QColor(self.REC_COLOR)
        dot_color.setAlphaF(self._dot_opacity)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(dot_color))
        dot_x = 24
        dot_y = self.PILL_HEIGHT // 2
        painter.drawEllipse(dot_x - 5, dot_y - 5, 10, 10)

        # Waveform bars
        bar_area_start = 50
        bar_area_width = self.PILL_WIDTH - 70
        bar_spacing = bar_area_width / self.BAR_COUNT
        bar_width = max(3, bar_spacing * 0.6)
        max_bar_height = self.PILL_HEIGHT - 16

        for i, height in enumerate(self._bar_heights):
            bar_h = max(3, height * max_bar_height)
            x = bar_area_start + i * bar_spacing + (bar_spacing - bar_width) / 2
            y = (self.PILL_HEIGHT - bar_h) / 2

            bar_color = QColor(self.REC_COLOR)
            bar_color.setAlphaF(0.6 + height * 0.4)
            painter.setBrush(QBrush(bar_color))
            painter.drawRoundedRect(int(x), int(y), int(bar_width), int(bar_h), 2, 2)

    def _paint_processing(self, painter):
        """Draw processing indicator: three animated dots."""
        painter.setPen(Qt.PenStyle.NoPen)
        center_x = self.PILL_WIDTH // 2
        center_y = self.PILL_HEIGHT // 2
        dot_spacing = 16

        for i in range(3):
            x = center_x + (i - 1) * dot_spacing
            is_active = (i == self._proc_dot_index)
            color = QColor(self.PROC_COLOR)
            color.setAlphaF(1.0 if is_active else 0.3)
            painter.setBrush(QBrush(color))
            radius = 5 if is_active else 4
            painter.drawEllipse(x - radius, center_y - radius, radius * 2, radius * 2)

    def _paint_typing(self, painter):
        """Draw typing/pasted/complete/error indicator."""
        font = QFont()
        font.setPixelSize(18)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(self._typing_color)

        text = self._typing_text
        if self._typing_show_dots:
            text += "." * self._typing_dot_count

        fm = QFontMetrics(font)
        # Reserve space for max dots so text doesn't shift
        if self._typing_show_dots:
            max_w = fm.horizontalAdvance(self._typing_text + "...")
        else:
            max_w = fm.horizontalAdvance(text)

        start_x = (self.PILL_WIDTH - max_w) // 2

        painter.drawText(
            QRect(start_x, 0, max_w, self.PILL_HEIGHT),
            Qt.AlignmentFlag.AlignVCenter,
            text,
        )
