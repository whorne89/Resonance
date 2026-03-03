"""
Live debug panel for Resonance.
Shows real-time pipeline info during transcription in a dark panel
anchored to the bottom-right corner of the screen.
"""

from PySide6.QtWidgets import QWidget, QPushButton
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QPainterPath, QFont,
    QGuiApplication, QFontMetrics,
)


class DebugPanel(QWidget):
    """
    Live debug panel showing pipeline steps in real time.

    Appears on hotkey press, fills in as each step completes,
    auto-dismisses after 15 seconds. X button to close early.
    """

    # Dimensions
    WIDTH = 380
    MIN_HEIGHT = 100
    MAX_HEIGHT = 600
    RADIUS = 12
    MARGIN = 20
    PADDING = 14

    # Colors
    BG_COLOR = QColor(26, 26, 46, 235)
    BORDER_COLOR = QColor(45, 45, 78, 128)
    ACCENT_COLOR = QColor(52, 152, 219)
    HEADER_COLOR = QColor(52, 152, 219)
    LABEL_COLOR = QColor(255, 255, 255, 220)
    VALUE_COLOR = QColor(255, 255, 255, 170)
    DIM_COLOR = QColor(255, 255, 255, 100)
    SUCCESS_COLOR = QColor(46, 204, 113)
    PENDING_COLOR = QColor(255, 255, 255, 80)

    # Timing
    AUTO_DISMISS_MS = 15000
    FADE_IN_MS = 200
    FADE_OUT_MS = 300

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # State
        self._sections = []  # list of (label, lines, status) tuples
        self._session_id = ""

        # Close button
        self._close_btn = QPushButton("\u2715", self)
        self._close_btn.setFixedSize(24, 24)
        self._close_btn.setStyleSheet(
            "QPushButton { background: transparent; color: rgba(255,255,255,120);"
            " border: none; font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { color: rgba(255,255,255,220); }"
        )
        self._close_btn.clicked.connect(self.dismiss)

        # Animation
        self._fade_anim = None

        # Auto-dismiss timer
        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self.dismiss)

    # ── Public API (called by VTTApplication) ────────────────────────

    def on_recording_started(self, data):
        """Show panel when recording begins."""
        self._sections = []
        self._session_id = data.get("session_id", "")
        self._dismiss_timer.stop()
        self._add_section("Recording", ["Started..."], "active")
        self._show_panel()

    def on_ocr_completed(self, data):
        """Update with OCR results."""
        timing = data.get("timing_ms", 0)
        app_type = data.get("app_type", "unknown")
        title = data.get("window_title", "")
        nouns = data.get("proper_nouns", [])

        lines = [f"App: {title[:40]}",  f"Type: {app_type.upper()}"]
        if nouns:
            lines.append(f"Names: {', '.join(nouns[:8])}")

        self._add_section(f"OCR \u2713 ({timing}ms)", lines, "done")
        self._refresh()

    def on_transcription_completed(self, data):
        """Update with Whisper results."""
        timing = data.get("timing_ms", 0)
        raw = data.get("raw_output", "")
        confidence = data.get("confidence", 0)
        model = data.get("model", "")

        lines = [
            f'"{raw[:80]}{"..." if len(raw) > 80 else ""}"',
            f"Confidence: {confidence:.0%}  |  Model: {model}",
        ]
        self._add_section(f"Whisper \u2713 ({timing}ms)", lines, "done")
        # Update recording section
        self._update_section("Recording", status="done")
        self._refresh()

    def on_post_processing_completed(self, data):
        """Update with post-processing results."""
        timing = data.get("timing_ms", 0)
        input_text = data.get("input", "")
        output_text = data.get("output", "")

        if input_text == output_text:
            lines = ["No changes"]
        else:
            lines = [
                f'In:  "{input_text[:60]}{"..." if len(input_text) > 60 else ""}"',
                f'Out: "{output_text[:60]}{"..." if len(output_text) > 60 else ""}"',
            ]
        self._add_section(f"Post-Processing \u2713 ({timing}ms)", lines, "done")
        self._refresh()

    def on_post_processing_skipped(self):
        """Mark post-processing as skipped."""
        self._add_section("Post-Processing", ["OFF"], "skipped")
        self._refresh()

    def on_text_cleanup_completed(self, data):
        """Update with text cleanup results."""
        input_text = data.get("input", "")
        output_text = data.get("output", "")
        comma = data.get("comma_spam_triggered", False)
        punct = data.get("spoken_punctuation_applied", False)

        if input_text == output_text:
            lines = ["No changes"]
        else:
            changes = []
            if comma:
                changes.append("comma spam cleaned")
            if punct:
                changes.append("spoken punctuation applied")
            lines = [", ".join(changes) if changes else "Text modified"]
        self._add_section("Text Cleanup \u2713", lines, "done")
        self._refresh()

    def on_dictionary_completed(self, data):
        """Update with dictionary results."""
        replacements = data.get("replacements_applied", {})
        if replacements:
            lines = [f"{k} \u2192 {v}" for k, v in list(replacements.items())[:5]]
        else:
            lines = ["No replacements"]
        self._add_section("Dictionary \u2713", lines, "done")
        self._refresh()

    def on_session_completed(self, data):
        """Show final result and start dismiss timer."""
        final = data.get("final_text", "")
        total = data.get("timing", {}).get("total_ms", 0)

        lines = [
            f'"{final[:80]}{"..." if len(final) > 80 else ""}"',
            f"Total: {total}ms",
        ]
        self._add_section("Final", lines, "done")
        self._refresh()
        self._dismiss_timer.start(self.AUTO_DISMISS_MS)

    # ── Internal ─────────────────────────────────────────────────────

    def _add_section(self, label, lines, status="pending"):
        """Add a section to the panel."""
        # Replace existing section with same base label
        base = label.split(" \u2713")[0].split(" ...")[0]
        for i, (existing_label, _, _) in enumerate(self._sections):
            existing_base = existing_label.split(" \u2713")[0].split(" ...")[0]
            if existing_base == base:
                self._sections[i] = (label, lines, status)
                return
        self._sections.append((label, lines, status))

    def _update_section(self, base_label, status=None, lines=None):
        """Update an existing section's status or lines."""
        for i, (label, existing_lines, existing_status) in enumerate(self._sections):
            if label.startswith(base_label):
                new_lines = lines if lines is not None else existing_lines
                new_status = status if status is not None else existing_status
                self._sections[i] = (label, new_lines, new_status)
                return

    def _refresh(self):
        """Recalculate height and repaint."""
        height = self._calculate_height()
        self.setFixedSize(self.WIDTH, min(height, self.MAX_HEIGHT))
        self._position_on_screen()
        self._close_btn.move(self.WIDTH - 30, 6)
        self.update()

    def _calculate_height(self):
        """Calculate needed height based on sections."""
        # Header + padding
        h = self.PADDING + 24 + 8  # top pad + header + gap
        line_height = 16
        section_gap = 12
        label_height = 18

        for label, lines, status in self._sections:
            h += label_height + 4  # section label
            h += len(lines) * line_height  # content lines
            h += section_gap  # gap between sections

        h += self.PADDING  # bottom padding
        return max(self.MIN_HEIGHT, h)

    def _show_panel(self):
        """Show the panel with fade-in."""
        self._refresh()
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()

        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(self.FADE_IN_MS)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._fade_anim.start()

    def dismiss(self):
        """Fade out and hide."""
        self._dismiss_timer.stop()
        if self._fade_anim is not None:
            self._fade_anim.stop()

        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(self.FADE_OUT_MS)
        self._fade_anim.setStartValue(self.windowOpacity())
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._fade_anim.finished.connect(self.hide)
        self._fade_anim.start()

    def _position_on_screen(self):
        """Position at bottom-right of primary screen."""
        screen = QGuiApplication.primaryScreen()
        if screen:
            geom = screen.availableGeometry()
            x = geom.x() + geom.width() - self.WIDTH - self.MARGIN
            y = geom.y() + geom.height() - self.height() - self.MARGIN
            self.move(x, y)

    def paintEvent(self, event):
        """Draw the debug panel."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        # Background
        path = QPainterPath()
        path.addRoundedRect(0.5, 0.5, w - 1, h - 1, self.RADIUS, self.RADIUS)
        painter.setPen(QPen(self.BORDER_COLOR, 1))
        painter.setBrush(QBrush(self.BG_COLOR))
        painter.drawPath(path)

        # Left accent bar
        painter.setClipPath(path)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self.ACCENT_COLOR))
        painter.drawRoundedRect(0, 0, 3, h, 1, 1)
        painter.setClipping(False)

        # Header: "DEBUG"
        x = self.PADDING
        y = self.PADDING + 14

        header_font = QFont()
        header_font.setPixelSize(13)
        header_font.setBold(True)
        header_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2)
        painter.setFont(header_font)
        painter.setPen(self.HEADER_COLOR)
        painter.drawText(x, y, "DEBUG")

        y += 12

        # Sections
        label_font = QFont()
        label_font.setPixelSize(12)
        label_font.setBold(True)

        value_font = QFont()
        value_font.setPixelSize(11)

        line_height = 16
        section_gap = 12

        for label, lines, status in self._sections:
            y += section_gap

            # Section label
            painter.setFont(label_font)
            if status == "done":
                painter.setPen(self.SUCCESS_COLOR)
            elif status == "active":
                painter.setPen(self.ACCENT_COLOR)
            elif status == "skipped":
                painter.setPen(self.DIM_COLOR)
            else:
                painter.setPen(self.PENDING_COLOR)

            painter.drawText(x, y, label)
            y += 4

            # Content lines
            painter.setFont(value_font)
            if status == "skipped":
                painter.setPen(self.DIM_COLOR)
            else:
                painter.setPen(self.VALUE_COLOR)

            for line in lines:
                y += line_height
                # Truncate long lines
                metrics = QFontMetrics(value_font)
                max_w = self.WIDTH - self.PADDING * 2 - 10
                elided = metrics.elidedText(line, Qt.TextElideMode.ElideRight, max_w)
                painter.drawText(x + 8, y, elided)

        painter.end()
