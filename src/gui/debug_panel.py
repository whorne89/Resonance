"""
Live debug panel for Resonance.
Shows real-time pipeline info during transcription in a dark panel
anchored to the bottom-right corner of the screen.
"""

from PySide6.QtWidgets import QWidget, QPushButton
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QEvent, QRect
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QPainterPath, QFont,
    QGuiApplication, QFontMetrics,
)


class DebugPanel(QWidget):
    """
    Live debug panel showing pipeline steps in real time.

    Appears on hotkey press, fills in progressively as each pipeline
    step completes, auto-dismisses after 25 seconds.
    """

    # Dimensions
    WIDTH = 480
    MIN_HEIGHT = 80
    MAX_HEIGHT = 800
    RADIUS = 14
    MARGIN = 20
    PADDING = 22
    CONTENT_INDENT = 14

    # Colors (matching Resonance toast/overlay palette)
    BG_COLOR = QColor(26, 26, 46, 240)
    BORDER_COLOR = QColor(45, 45, 78, 128)
    ACCENT_COLOR = QColor(52, 152, 219)
    HEADER_COLOR = QColor(52, 152, 219)
    VALUE_COLOR = QColor(255, 255, 255, 180)
    DIM_COLOR = QColor(255, 255, 255, 80)
    SUCCESS_COLOR = QColor(46, 204, 113)
    ACTIVE_COLOR = QColor(52, 152, 219)
    SEPARATOR_COLOR = QColor(255, 255, 255, 25)

    # Timing
    AUTO_DISMISS_MS = 25000
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

        # Close button — painted manually in paintEvent for reliable rendering;
        # this invisible QPushButton handles the click target only.
        self._close_btn = QPushButton("", self)
        self._close_btn.setFixedSize(28, 28)
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; }"
        )
        self._close_btn.clicked.connect(self.dismiss)
        self._close_btn.installEventFilter(self)

        # Animation
        self._fade_anim = None

        # Auto-dismiss timer
        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self.dismiss)

        # Fonts
        self._header_font = QFont("Segoe UI", 18, QFont.Weight.Bold)
        self._header_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3)

        self._label_font = QFont("Segoe UI", 11, QFont.Weight.DemiBold)

        self._value_font = QFont("Segoe UI", 10)

    # ── Public API ───────────────────────────────────────────────────

    @staticmethod
    def _fmt_time(ms):
        """Format milliseconds as 'Xs (Yms)'."""
        return f"{ms / 1000:.1f}s ({ms}ms)"

    def on_recording_started(self, data):
        """Show panel when recording begins."""
        self._sections = []
        self._session_id = data.get("session_id", "")
        self._dismiss_timer.stop()
        self._add_section("Recording", ["Listening..."], "active")
        self._show_panel()

    def on_recording_stopped(self, data):
        """Update recording section when recording stops."""
        duration = data.get("duration_seconds", 0)
        self._add_section(
            f"Recording  \u2713  {duration:.1f}s",
            [f"Duration: {duration:.1f}s", "Processing..."],
            "done",
        )
        self._refresh()

    def on_ocr_skipped(self):
        """Mark OCR as skipped/off."""
        self._add_section("OCR", ["OFF"], "skipped")
        self._refresh()

    def on_ocr_completed(self, data):
        """Update with OCR results."""
        timing = data.get("timing_ms", 0)
        app_type = data.get("app_type", "unknown")
        title = data.get("window_title", "")
        nouns = data.get("proper_nouns", [])

        lines = [f"App: {title}", f"Type: {app_type.upper()}"]
        if nouns:
            lines.append(f"Names: {', '.join(nouns)}")

        self._add_section(f"OCR  \u2713  {self._fmt_time(timing)}", lines, "done")
        self._refresh()

    def on_transcription_completed(self, data):
        """Update with Whisper results."""
        timing = data.get("timing_ms", 0)
        raw = data.get("raw_output", "")
        confidence = data.get("confidence", 0)
        model = data.get("model", "")

        lines = [
            f'"{raw}"',
            f"Confidence: {confidence:.0%}   Model: {model}",
        ]
        self._add_section(f"Whisper  \u2713  {self._fmt_time(timing)}", lines, "done")
        # Clean up Recording section — remove "Processing..." now that transcription is done
        for i, (lbl, lns, _) in enumerate(self._sections):
            if lbl.startswith("Recording"):
                cleaned = [l for l in lns if l != "Processing..."]
                self._sections[i] = (lbl, cleaned or ["Done"], "done")
                break
        self._refresh()

    def on_post_processing_completed(self, data):
        """Update with post-processing results."""
        timing = data.get("timing_ms", 0)
        input_text = data.get("input", "")
        output_text = data.get("output", "")

        if input_text == output_text:
            lines = ["No changes"]
        else:
            lines = [f'"{output_text}"']

        self._add_section(f"Post-Processing  \u2713  {self._fmt_time(timing)}", lines, "done")
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
                changes.append("Comma spam cleaned")
            if punct:
                changes.append("Spoken punctuation applied")
            lines = [", ".join(changes) if changes else "Text modified"]
        self._add_section("Text Cleanup  \u2713", lines, "done")
        self._refresh()

    def on_dictionary_completed(self, data):
        """Update with dictionary results."""
        replacements = data.get("replacements_applied", {})
        if replacements:
            lines = [f"{k} \u2192 {v}" for k, v in list(replacements.items())[:5]]
        else:
            lines = ["No replacements"]
        self._add_section("Dictionary  \u2713", lines, "done")
        self._refresh()

    def on_learning_completed(self, data):
        """Update with learning engine data."""
        if not data.get("enabled"):
            self._add_section("Learning", ["OFF"], "skipped")
            self._refresh()
            return

        app_key = data.get("app_key", "")
        vocab = data.get("vocabulary_injected", [])
        style = data.get("style_metrics", {})
        suffix = data.get("style_suffix", "")
        sessions = data.get("sessions_count", 0)
        confidence = data.get("confidence", 0)

        lines = []
        if app_key:
            lines.append(f"App: {app_key} ({sessions} sessions, {confidence:.0%} confidence)")
        if vocab:
            lines.append(f"Vocab injected: {', '.join(vocab[:8])}")

        # Show style metrics
        formality = style.get("formality_score", 0)
        punct = style.get("punctuation_ratio", 0)
        cap = style.get("capitalization_ratio", 0)
        abbrev = style.get("abbreviation_count", 0)
        samples = style.get("sample_count", 0)

        if samples >= 3:
            lines.append(
                f"Style: formality {formality:.0%}, punct {punct:.0%}, "
                f"caps {cap:.0%}, abbrev {abbrev}"
            )
        elif samples > 0:
            lines.append(f"Style: {samples}/3 samples (not enough data yet)")

        if suffix:
            lines.append(f"Prompt: {suffix}")

        if not lines:
            lines = ["No profile data"]

        self._add_section("Learning  \u2713", lines, "done")
        self._refresh()

    def on_session_completed(self, data):
        """Show final result and start dismiss timer."""
        final = data.get("final_text", "")
        total = data.get("timing", {}).get("total_ms", 0)

        lines = [f'"{final}"']
        self._add_section(f"Result  \u2713  {self._fmt_time(total)}", lines, "done")
        self._refresh()
        self._dismiss_timer.start(self.AUTO_DISMISS_MS)

    # ── Internal ─────────────────────────────────────────────────────

    def _add_section(self, label, lines, status="pending"):
        """Add or replace a section."""
        base = label.split("  \u2713")[0].split(" ...")[0]
        for i, (existing_label, _, _) in enumerate(self._sections):
            existing_base = existing_label.split("  \u2713")[0].split(" ...")[0]
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

    def _content_width(self):
        """Available width for wrapped content text."""
        return self.WIDTH - self.PADDING * 2 - self.CONTENT_INDENT

    def _max_height(self):
        """Max height based on available screen space."""
        screen = QGuiApplication.primaryScreen()
        if screen:
            return screen.availableGeometry().height() - self.MARGIN * 2
        return self.MAX_HEIGHT

    def _refresh(self):
        """Recalculate size and repaint."""
        height = self._calculate_height()
        self.setFixedSize(self.WIDTH, min(height, self._max_height()))
        self._position_on_screen()
        self._close_btn.move(self.WIDTH - 36, 10)
        self._close_btn.raise_()
        self.update()

    def _calculate_height(self):
        """Calculate needed height with word-wrapped content.

        Must mirror the exact y-advancement logic in paintEvent.
        """
        # Header: matches paintEvent — PADDING + 22 (baseline) + 12 (sep) + 4 (gap)
        h = self.PADDING + 22 + 12 + 4
        section_gap = 16
        label_advance = 2  # matches paintEvent: drawText at y, then y += 2
        content_gap = 4

        metrics = QFontMetrics(self._value_font)
        max_w = self._content_width()

        for label, lines, status in self._sections:
            h += section_gap
            h += label_advance  # section label baseline advance
            for line in lines:
                bounding = metrics.boundingRect(
                    QRect(0, 0, max_w, 0),
                    Qt.TextFlag.TextWordWrap, line,
                )
                h += bounding.height() + content_gap

        h += 8  # bottom breathing room
        return max(self.MIN_HEIGHT, h)

    def _show_panel(self):
        """Show with fade-in."""
        self._refresh()
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        self._close_btn.raise_()
        self._close_btn.show()

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

    def eventFilter(self, obj, event):
        """Repaint when mouse enters/leaves the close button."""
        if obj is self._close_btn and event.type() in (QEvent.Type.Enter, QEvent.Type.Leave):
            self.update()
        return super().eventFilter(obj, event)

    def paintEvent(self, event):
        """Draw the debug panel."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        x = self.PADDING
        content_x = x + self.CONTENT_INDENT
        content_max_w = self._content_width()
        section_gap = 16
        content_gap = 4

        # ── Background ───────────────────────────────────────────
        bg_path = QPainterPath()
        bg_path.addRoundedRect(0.5, 0.5, w - 1, h - 1, self.RADIUS, self.RADIUS)
        painter.setPen(QPen(self.BORDER_COLOR, 1))
        painter.setBrush(QBrush(self.BG_COLOR))
        painter.drawPath(bg_path)

        # Left accent bar
        painter.setClipPath(bg_path)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self.ACCENT_COLOR))
        painter.drawRoundedRect(0, 0, 4, h, 2, 2)
        painter.setClipping(False)

        # ── Close button (X) ────────────────────────────────────
        btn = self._close_btn.geometry()
        btn_hovered = self._close_btn.underMouse()
        if btn_hovered:
            painter.setBrush(QBrush(QColor(231, 76, 60, 80)))
            painter.setPen(QPen(QColor(231, 76, 60, 120), 1))
        else:
            painter.setBrush(QBrush(QColor(255, 255, 255, 15)))
            painter.setPen(QPen(QColor(255, 255, 255, 30), 1))
        painter.drawRoundedRect(btn, 14, 14)

        x_font = QFont("Segoe UI", 10, QFont.Weight.Bold)
        painter.setFont(x_font)
        painter.setPen(QColor(231, 76, 60) if btn_hovered else QColor(255, 255, 255, 180))
        painter.drawText(btn, Qt.AlignmentFlag.AlignCenter, "X")

        # ── Header ───────────────────────────────────────────────
        y = self.PADDING + 22

        painter.setFont(self._header_font)
        painter.setPen(self.HEADER_COLOR)
        painter.drawText(x, y, "DEBUG PIPELINE")

        # Thin separator
        y += 12
        painter.setPen(QPen(self.SEPARATOR_COLOR, 1))
        painter.drawLine(x, y, w - self.PADDING, y)
        y += 4

        # ── Sections ─────────────────────────────────────────────
        for label, lines, status in self._sections:
            y += section_gap

            # Section label
            painter.setFont(self._label_font)
            if status == "done":
                painter.setPen(self.SUCCESS_COLOR)
            elif status == "active":
                painter.setPen(self.ACTIVE_COLOR)
            elif status == "skipped":
                painter.setPen(self.DIM_COLOR)
            else:
                painter.setPen(QColor(255, 255, 255, 60))

            painter.drawText(x, y, label)
            y += 2

            # Content lines (word-wrapped)
            painter.setFont(self._value_font)
            painter.setPen(self.DIM_COLOR if status == "skipped" else self.VALUE_COLOR)

            metrics = QFontMetrics(self._value_font)
            for line in lines:
                bounding = metrics.boundingRect(
                    QRect(0, 0, content_max_w, 0),
                    Qt.TextFlag.TextWordWrap, line,
                )
                text_rect = QRect(content_x, y, content_max_w, bounding.height())
                painter.drawText(text_rect, Qt.TextFlag.TextWordWrap, line)
                y += bounding.height() + content_gap

        painter.end()
