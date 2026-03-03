# Debug Mode Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a Debug section to Settings with session logging, a live debug panel, and an HTML comparison report generator.

**Architecture:** A `DebugManager` (QObject) in `src/core/debug_manager.py` owns all debug state — it records pipeline steps in memory, writes session JSON to disk, emits Qt signals for the live panel, and generates HTML reports. A `DebugPanel` widget in `src/gui/debug_panel.py` subscribes to those signals and renders live pipeline info. Settings dialog gets a new Debug group with a master toggle, two sub-checkboxes, and a report button.

**Tech Stack:** PySide6 (Qt), JSON for session storage, string templating for HTML reports. No new dependencies.

---

### Task 1: Add debug config keys to ConfigManager

**Files:**
- Modify: `src/utils/config.py`

**Step 1: Add debug section to DEFAULT_CONFIG**

In `ConfigManager.DEFAULT_CONFIG`, after the `"statistics"` block (line 82), add:

```python
        "debug": {
            "enabled": False,
            "logging_enabled": False,
            "live_panel_enabled": False
        }
```

**Step 2: Add getter/setter methods**

After `reset_to_defaults()` (line 337), add:

```python
    def get_debug_enabled(self):
        """Get whether debug mode is enabled."""
        return self.get("debug", "enabled", default=False)

    def set_debug_enabled(self, enabled):
        """Set whether debug mode is enabled."""
        self.set("debug", "enabled", value=enabled)

    def get_debug_logging_enabled(self):
        """Get whether debug session logging is enabled."""
        return self.get("debug", "logging_enabled", default=False)

    def set_debug_logging_enabled(self, enabled):
        """Set whether debug session logging is enabled."""
        self.set("debug", "logging_enabled", value=enabled)

    def get_debug_live_panel_enabled(self):
        """Get whether the live debug panel is enabled."""
        return self.get("debug", "live_panel_enabled", default=False)

    def set_debug_live_panel_enabled(self, enabled):
        """Set whether the live debug panel is enabled."""
        self.set("debug", "live_panel_enabled", value=enabled)
```

**Step 3: Commit**

```bash
git add src/utils/config.py
git commit -m "feat: add debug mode config keys"
```

---

### Task 2: Create DebugManager core module

**Files:**
- Create: `src/core/debug_manager.py`

**Step 1: Create the DebugManager class**

```python
"""
Debug manager for Resonance.
Handles session logging, pipeline step recording, and HTML report generation.
Emits Qt signals for the live debug panel to consume.
"""

import json
import time
import uuid
import webbrowser
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from utils.logger import get_logger
from utils.resource_path import get_app_data_path


# Max session files to keep on disk
MAX_SESSION_FILES = 500


class DebugManager(QObject):
    """
    Manages debug session data, logging, and report generation.

    Emits signals at each pipeline step so the DebugPanel can update live.
    Holds the current session in memory; writes to disk on completion
    if logging is enabled.
    """

    # Signals for live debug panel updates
    recording_started = Signal(dict)    # {"timestamp": ..., "session_id": ...}
    ocr_completed = Signal(dict)        # {"app_type": ..., "proper_nouns": ..., "timing_ms": ...}
    transcription_completed = Signal(dict)  # {"raw_output": ..., "confidence": ..., "timing_ms": ...}
    post_processing_completed = Signal(dict)  # {"input": ..., "output": ..., "timing_ms": ...}
    text_cleanup_completed = Signal(dict)    # {"input": ..., "output": ..., "comma_spam": ..., "spoken_punct": ...}
    dictionary_completed = Signal(dict)      # {"replacements_applied": ..., "output": ...}
    session_completed = Signal(dict)         # full session dict

    def __init__(self, logging_enabled=False, live_panel_enabled=False):
        super().__init__()
        self.logger = get_logger()
        self._logging_enabled = logging_enabled
        self._live_panel_enabled = live_panel_enabled
        self._session_dir = Path(get_app_data_path("debug")) / "sessions"
        self._current_session = None
        self._step_start_time = None

    @property
    def logging_enabled(self):
        return self._logging_enabled

    @logging_enabled.setter
    def logging_enabled(self, value):
        self._logging_enabled = value

    @property
    def live_panel_enabled(self):
        return self._live_panel_enabled

    @live_panel_enabled.setter
    def live_panel_enabled(self, value):
        self._live_panel_enabled = value

    # ── Session lifecycle ────────────────────────────────────────────

    def start_session(self):
        """Begin a new debug session. Call when recording starts."""
        self._current_session = {
            "session_id": uuid.uuid4().hex[:8],
            "timestamp": datetime.now().isoformat(),
            "audio": {},
            "timing": {},
            "ocr": {"enabled": False},
            "whisper": {},
            "post_processing": {"enabled": False},
            "text_cleanup": {},
            "dictionary": {},
            "final_text": "",
            "delivery": {},
            "learning": {"enabled": False},
        }
        self._step_start_time = time.perf_counter()

        if self._live_panel_enabled:
            self.recording_started.emit({
                "timestamp": self._current_session["timestamp"],
                "session_id": self._current_session["session_id"],
            })

    def record_audio(self, duration_seconds, avg_rms, sample_rate):
        """Record audio stats after recording stops."""
        if not self._current_session:
            return
        self._current_session["audio"] = {
            "duration_seconds": round(duration_seconds, 2),
            "avg_rms": round(avg_rms, 4),
            "sample_rate": sample_rate,
        }

    def start_step(self):
        """Mark the start of a timed pipeline step."""
        self._step_start_time = time.perf_counter()

    def _elapsed_ms(self):
        """Get milliseconds since last start_step() call."""
        if self._step_start_time is None:
            return 0
        return round((time.perf_counter() - self._step_start_time) * 1000)

    def record_ocr(self, app_type, window_title, proper_nouns, raw_text_length):
        """Record OCR results."""
        if not self._current_session:
            return
        elapsed = self._elapsed_ms()
        ocr_data = {
            "enabled": True,
            "app_type": app_type,
            "window_title": window_title,
            "proper_nouns": proper_nouns,
            "raw_text_length": raw_text_length,
        }
        self._current_session["ocr"] = ocr_data
        self._current_session["timing"]["ocr_ms"] = elapsed

        if self._live_panel_enabled:
            self.ocr_completed.emit({**ocr_data, "timing_ms": elapsed})

    def record_transcription(self, model, raw_output, confidence, initial_prompt):
        """Record Whisper transcription results."""
        if not self._current_session:
            return
        elapsed = self._elapsed_ms()
        whisper_data = {
            "model": model,
            "raw_output": raw_output,
            "confidence": round(confidence, 3),
            "initial_prompt": initial_prompt or "",
        }
        self._current_session["whisper"] = whisper_data
        self._current_session["timing"]["transcription_ms"] = elapsed

        if self._live_panel_enabled:
            self.transcription_completed.emit({**whisper_data, "timing_ms": elapsed})

    def record_post_processing(self, input_text, output_text, system_prompt_type):
        """Record post-processing results."""
        if not self._current_session:
            return
        elapsed = self._elapsed_ms()
        pp_data = {
            "enabled": True,
            "input": input_text,
            "output": output_text,
            "system_prompt_type": system_prompt_type or "",
        }
        self._current_session["post_processing"] = pp_data
        self._current_session["timing"]["post_processing_ms"] = elapsed

        if self._live_panel_enabled:
            self.post_processing_completed.emit({**pp_data, "timing_ms": elapsed})

    def record_text_cleanup(self, input_text, output_text, comma_spam_triggered, spoken_punctuation_applied):
        """Record text cleanup results."""
        if not self._current_session:
            return
        cleanup_data = {
            "input": input_text,
            "output": output_text,
            "comma_spam_triggered": comma_spam_triggered,
            "spoken_punctuation_applied": spoken_punctuation_applied,
        }
        self._current_session["text_cleanup"] = cleanup_data

        if self._live_panel_enabled:
            self.text_cleanup_completed.emit(cleanup_data)

    def record_dictionary(self, replacements_applied, output_text):
        """Record dictionary replacement results."""
        if not self._current_session:
            return
        dict_data = {
            "replacements_applied": replacements_applied,
            "output": output_text,
        }
        self._current_session["dictionary"] = dict_data

        if self._live_panel_enabled:
            self.dictionary_completed.emit(dict_data)

    def record_learning(self, enabled, app_key, vocabulary_injected, style_suffix):
        """Record learning engine data."""
        if not self._current_session:
            return
        self._current_session["learning"] = {
            "enabled": enabled,
            "app_key": app_key or "",
            "vocabulary_injected": vocabulary_injected or [],
            "style_suffix": style_suffix or "",
        }

    def record_delivery(self, method, char_count):
        """Record how text was delivered."""
        if not self._current_session:
            return
        self._current_session["delivery"] = {
            "method": method,
            "char_count": char_count,
        }

    def finish_session(self, final_text):
        """Complete the session. Writes to disk if logging enabled."""
        if not self._current_session:
            return

        self._current_session["final_text"] = final_text

        # Calculate total time from session start
        start = datetime.fromisoformat(self._current_session["timestamp"])
        total_ms = round((datetime.now() - start).total_seconds() * 1000)
        self._current_session["timing"]["total_ms"] = total_ms

        if self._live_panel_enabled:
            self.session_completed.emit(self._current_session)

        if self._logging_enabled:
            self._write_session(self._current_session)

        self._current_session = None

    # ── Persistence ──────────────────────────────────────────────────

    def _write_session(self, session):
        """Write a session dict to a JSON file."""
        try:
            self._session_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.fromisoformat(session["timestamp"])
            filename = f"session_{ts.strftime('%Y-%m-%d_%H%M%S')}_{session['session_id']}.json"
            filepath = self._session_dir / filename

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(session, f, indent=2, ensure_ascii=False)

            self.logger.info(f"Debug session saved: {filename}")
            self._enforce_limit()
        except Exception as e:
            self.logger.error(f"Failed to write debug session: {e}")

    def _enforce_limit(self):
        """Remove oldest session files if over the limit."""
        try:
            files = sorted(self._session_dir.glob("session_*.json"))
            if len(files) > MAX_SESSION_FILES:
                for f in files[:len(files) - MAX_SESSION_FILES]:
                    f.unlink()
                    self.logger.info(f"Cleaned old debug session: {f.name}")
        except Exception as e:
            self.logger.error(f"Failed to clean debug sessions: {e}")

    # ── HTML report ──────────────────────────────────────────────────

    def generate_report(self):
        """Generate an HTML comparison report and open in browser."""
        sessions = self._load_sessions(limit=100)
        if not sessions:
            self.logger.warning("No debug sessions found for report")
            return False

        html = self._build_html(sessions)
        report_path = Path(get_app_data_path("debug")) / "comparison_report.html"
        report_path.parent.mkdir(parents=True, exist_ok=True)

        with open(report_path, "w", encoding="utf-8") as f:
            f.write(html)

        webbrowser.open(str(report_path))
        self.logger.info(f"Debug report opened: {report_path}")
        return True

    def _load_sessions(self, limit=100):
        """Load recent session files, newest first."""
        if not self._session_dir.exists():
            return []
        files = sorted(self._session_dir.glob("session_*.json"), reverse=True)
        sessions = []
        for f in files[:limit]:
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    sessions.append(json.load(fh))
            except Exception:
                continue
        return sessions

    def _build_html(self, sessions):
        """Build an HTML comparison report from session data."""
        rows = []
        for s in sessions:
            confidence = s.get("whisper", {}).get("confidence", 0)
            if confidence > 0.85:
                conf_class = "high"
            elif confidence > 0.70:
                conf_class = "medium"
            else:
                conf_class = "low"

            app_type = s.get("ocr", {}).get("app_type", "—")
            whisper_raw = s.get("whisper", {}).get("raw_output", "—")
            pp_output = s.get("post_processing", {}).get("output", "—")
            if not s.get("post_processing", {}).get("enabled"):
                pp_output = "<em>OFF</em>"
            final = s.get("final_text", "—")
            ts = s.get("timestamp", "—")
            timing = s.get("timing", {})
            total = timing.get("total_ms", "—")

            rows.append(f"""<tr>
                <td>{ts}</td>
                <td>{app_type}</td>
                <td>{whisper_raw}</td>
                <td>{pp_output}</td>
                <td>{final}</td>
                <td class="{conf_class}">{confidence:.0%}</td>
                <td>{total}ms</td>
            </tr>""")

        rows_html = "\n".join(rows)

        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Resonance Debug Report</title>
<style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           background: #1a1a2e; color: #e0e0e0; padding: 20px; }}
    h1 {{ color: #3498db; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
    th {{ background: #2d2d4e; padding: 10px; text-align: left; font-size: 13px;
         border-bottom: 2px solid #3498db; }}
    td {{ padding: 8px 10px; border-bottom: 1px solid #2d2d4e; font-size: 12px;
         vertical-align: top; max-width: 300px; word-wrap: break-word; }}
    tr:hover {{ background: #2d2d4e; }}
    .high {{ color: #2ecc71; font-weight: bold; }}
    .medium {{ color: #f39c12; font-weight: bold; }}
    .low {{ color: #e74c3c; font-weight: bold; }}
    em {{ color: #666; }}
    .count {{ color: #888; margin-bottom: 20px; }}
</style>
</head>
<body>
<h1>Resonance Debug Report</h1>
<p class="count">{len(sessions)} sessions</p>
<table>
<thead>
    <tr>
        <th>Timestamp</th>
        <th>App Type</th>
        <th>Whisper Raw</th>
        <th>Post-Processed</th>
        <th>Final Text</th>
        <th>Confidence</th>
        <th>Total Time</th>
    </tr>
</thead>
<tbody>
{rows_html}
</tbody>
</table>
</body>
</html>"""

    def get_session_count(self):
        """Return number of saved session files."""
        if not self._session_dir.exists():
            return 0
        return len(list(self._session_dir.glob("session_*.json")))
```

**Step 2: Commit**

```bash
git add src/core/debug_manager.py
git commit -m "feat: add DebugManager for session logging and report generation"
```

---

### Task 3: Create DebugPanel widget

**Files:**
- Create: `src/gui/debug_panel.py`

**Step 1: Create the DebugPanel class**

Model after `UpdateToast` — frameless, always-on-top, semi-transparent dark panel, bottom-right corner. NOT click-through (has X button). 15s auto-dismiss after session completion.

```python
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
```

**Step 2: Commit**

```bash
git add src/gui/debug_panel.py
git commit -m "feat: add DebugPanel live pipeline view widget"
```

---

### Task 4: Add Debug section to Settings dialog

**Files:**
- Modify: `src/gui/settings_dialog.py`

**Step 1: Add `create_debug_group` method**

Add this method after `create_bug_report_group()` (around line 1265):

```python
    def create_debug_group(self):
        """Create debug mode configuration group."""
        group = QGroupBox("Debug")
        layout = QVBoxLayout()

        # Master toggle
        self.debug_enabled_cb = QCheckBox("Enable Debug Mode")
        debug_desc = QLabel(
            "Development tools for monitoring and refining transcription quality."
        )
        debug_desc.setWordWrap(True)
        debug_desc.setStyleSheet("color: rgba(255, 255, 255, 140); font-size: 11px;")
        layout.addWidget(self.debug_enabled_cb)
        layout.addWidget(debug_desc)

        # Sub-options container (hidden when debug mode off)
        self._debug_options_widget = QWidget()
        debug_options_layout = QVBoxLayout()
        debug_options_layout.setContentsMargins(20, 4, 0, 0)

        # Logging toggle
        self.debug_logging_cb = QCheckBox("Log Full Pipeline Data")
        logging_desc = QLabel(
            "Saves detailed session data for every transcription — audio stats, "
            "OCR results, Whisper output, post-processing changes, and final text."
        )
        logging_desc.setWordWrap(True)
        logging_desc.setStyleSheet("color: rgba(255, 255, 255, 140); font-size: 11px;")
        debug_options_layout.addWidget(self.debug_logging_cb)
        debug_options_layout.addWidget(logging_desc)

        # Live panel toggle
        self.debug_panel_cb = QCheckBox("Live Debug Panel")
        panel_desc = QLabel(
            "Shows real-time pipeline info in the corner during transcription."
        )
        panel_desc.setWordWrap(True)
        panel_desc.setStyleSheet("color: rgba(255, 255, 255, 140); font-size: 11px;")
        debug_options_layout.addWidget(self.debug_panel_cb)
        debug_options_layout.addWidget(panel_desc)

        # Report button
        report_row = QHBoxLayout()
        self._debug_report_btn = QPushButton("Open Comparison Report")
        self._debug_report_btn.setEnabled(False)
        self._debug_report_btn.clicked.connect(self._open_debug_report)
        report_row.addWidget(self._debug_report_btn)
        report_row.addStretch()
        debug_options_layout.addLayout(report_row)

        self._debug_session_count = QLabel("")
        self._debug_session_count.setStyleSheet("color: rgba(255, 255, 255, 100); font-size: 11px;")
        debug_options_layout.addWidget(self._debug_session_count)

        self._debug_options_widget.setLayout(debug_options_layout)
        layout.addWidget(self._debug_options_widget)

        # Wire dependency: debug mode gates sub-options
        self.debug_enabled_cb.stateChanged.connect(self._on_debug_toggled)
        self.debug_logging_cb.stateChanged.connect(self._on_debug_logging_toggled)

        group.setLayout(layout)
        return group

    def _on_debug_toggled(self, state=None):
        """Show/hide debug sub-options based on master toggle."""
        enabled = self.debug_enabled_cb.isChecked()
        self._debug_options_widget.setVisible(enabled)
        if not enabled:
            self.debug_logging_cb.setChecked(False)
            self.debug_panel_cb.setChecked(False)

    def _on_debug_logging_toggled(self, state=None):
        """Enable/disable report button based on logging toggle."""
        self._debug_report_btn.setEnabled(self.debug_logging_cb.isChecked())

    def _open_debug_report(self):
        """Generate and open the HTML comparison report."""
        from core.debug_manager import DebugManager
        dm = DebugManager(logging_enabled=True)
        count = dm.get_session_count()
        if count == 0:
            MessageBox.information(
                self, "No Data",
                "No debug sessions recorded yet. Enable logging and use Resonance to collect data."
            )
            return
        dm.generate_report()
```

**Step 2: Add the debug group to init_ui**

In `init_ui()`, after the bug report group (line 707), add:

```python
        # Debug
        debug_group = self.create_debug_group()
        content_layout.addWidget(debug_group)
```

**Step 3: Load debug settings in `load_current_settings`**

After the learning checkbox load (around line 1413), add:

```python
        # Debug mode
        self.debug_enabled_cb.setChecked(self.config.get_debug_enabled())
        self.debug_logging_cb.setChecked(self.config.get_debug_logging_enabled())
        self.debug_panel_cb.setChecked(self.config.get_debug_live_panel_enabled())
        self._on_debug_toggled()  # Apply visibility
        self._on_debug_logging_toggled()  # Apply report button state

        # Update session count label
        from core.debug_manager import DebugManager
        dm = DebugManager()
        count = dm.get_session_count()
        if count > 0:
            self._debug_session_count.setText(f"{count} session(s) logged")
        else:
            self._debug_session_count.setText("")
```

**Step 4: Save debug settings in `save_settings`**

In `save_settings()`, after reading `learning_enabled` (line 1425), add:

```python
            debug_enabled = self.debug_enabled_cb.isChecked()
            debug_logging = self.debug_logging_cb.isChecked()
            debug_panel = self.debug_panel_cb.isChecked()
```

In the change detection block (after the learning change check, around line 1460), add:

```python
            old_debug = self.config.get_debug_enabled()
            old_debug_logging = self.config.get_debug_logging_enabled()
            old_debug_panel = self.config.get_debug_live_panel_enabled()
            if debug_enabled != old_debug:
                changes.append(f"Debug Mode \u2192 {'On' if debug_enabled else 'Off'}")
            if debug_logging != old_debug_logging:
                changes.append(f"Debug Logging \u2192 {'On' if debug_logging else 'Off'}")
            if debug_panel != old_debug_panel:
                changes.append(f"Debug Panel \u2192 {'On' if debug_panel else 'Off'}")
```

In the save-to-config block (after `set_learning_enabled`, around line 1503), add:

```python
            self.config.set_debug_enabled(debug_enabled)
            self.config.set_debug_logging_enabled(debug_logging)
            self.config.set_debug_live_panel_enabled(debug_panel)
```

**Step 5: Commit**

```bash
git add src/gui/settings_dialog.py
git commit -m "feat: add Debug section to settings dialog"
```

---

### Task 5: Wire DebugManager into the transcription pipeline

**Files:**
- Modify: `src/main.py`

This is the core integration — DebugManager gets called at each pipeline step.

**Step 1: Import and create DebugManager in VTTApplication.__init__**

After the existing imports at the top, add:

```python
from core.debug_manager import DebugManager
```

In `VTTApplication.__init__()`, after the learning engine initialization, add:

```python
        # Debug manager (created if debug mode enabled)
        self.debug_manager = None
        self.debug_panel = None
        self._init_debug()
```

Add the `_init_debug` method:

```python
    def _init_debug(self):
        """Initialize or tear down debug manager based on config."""
        debug_enabled = self.config.get_debug_enabled()

        if debug_enabled:
            if self.debug_manager is None:
                self.debug_manager = DebugManager(
                    logging_enabled=self.config.get_debug_logging_enabled(),
                    live_panel_enabled=self.config.get_debug_live_panel_enabled(),
                )

                # Create live panel if enabled
                if self.config.get_debug_live_panel_enabled():
                    from gui.debug_panel import DebugPanel
                    self.debug_panel = DebugPanel()
                    # Connect signals
                    self.debug_manager.recording_started.connect(self.debug_panel.on_recording_started)
                    self.debug_manager.ocr_completed.connect(self.debug_panel.on_ocr_completed)
                    self.debug_manager.transcription_completed.connect(self.debug_panel.on_transcription_completed)
                    self.debug_manager.post_processing_completed.connect(self.debug_panel.on_post_processing_completed)
                    self.debug_manager.text_cleanup_completed.connect(self.debug_panel.on_text_cleanup_completed)
                    self.debug_manager.dictionary_completed.connect(self.debug_panel.on_dictionary_completed)
                    self.debug_manager.session_completed.connect(self.debug_panel.on_session_completed)
            else:
                # Update settings on existing manager
                self.debug_manager.logging_enabled = self.config.get_debug_logging_enabled()
                self.debug_manager.live_panel_enabled = self.config.get_debug_live_panel_enabled()
        else:
            if self.debug_panel:
                self.debug_panel.dismiss()
                self.debug_panel.deleteLater()
                self.debug_panel = None
            self.debug_manager = None
```

**Step 2: Call `_init_debug()` from `on_settings_changed`**

In the existing `on_settings_changed()` method, add at the end:

```python
        # Refresh debug manager
        self._init_debug()
```

**Step 3: Instrument `on_hotkey_press`**

At the start of `on_hotkey_press()`, after the logging line (line 325), add:

```python
            if self.debug_manager:
                self.debug_manager.start_session()
```

Inside the `_capture_ocr` closure, after the OCR capture succeeds (after `self._current_ocr_context = self.screen_context.capture()`, line 336), add:

```python
                        if self._current_ocr_context and self.debug_manager:
                            ctx = self._current_ocr_context
                            self.debug_manager.record_ocr(
                                ctx.app_type.value, ctx.window_title,
                                ctx.proper_nouns, len(ctx.raw_text),
                            )
```

**Step 4: Instrument `on_hotkey_release`**

After getting audio data (after line 382 `self._last_audio_samples = len(audio_data)`), add:

```python
            if self.debug_manager:
                duration = len(audio_data) / self.audio_recorder.sample_rate
                self.debug_manager.record_audio(
                    duration, self.audio_recorder.current_rms,
                    self.audio_recorder.sample_rate,
                )
```

**Step 5: Instrument `start_transcription`**

After extracting learned vocabulary (around line 443), add:

```python
        if self.debug_manager:
            self.debug_manager.record_learning(
                enabled=self.learning_engine is not None,
                app_key=self.learning_engine.get_profile(
                    self._current_ocr_context.window_title
                ).app_key if self.learning_engine and self._current_ocr_context else None,
                vocabulary_injected=learned_vocabulary,
                style_suffix=style_suffix,
            )
            self.debug_manager.start_step()  # Start timing for transcription
```

**Step 6: Instrument TranscriptionWorker**

The TranscriptionWorker runs in a background thread but DebugManager signals need to be called from the main thread. The simplest approach: pass a `debug_data` dict back alongside the finished signal, then record everything in `on_transcription_complete`.

Modify `TranscriptionWorker.__init__` to accept `debug_enabled=False` parameter.

Add a `self._debug_data = {}` dict that collects pipeline step info during `run()`.

In `TranscriptionWorker.run()`, capture data at each step:

After `text = self.transcriber.transcribe(...)` (line 105):
```python
            if self.debug_enabled:
                self._debug_data["whisper_raw"] = text
                self._debug_data["whisper_confidence"] = getattr(self.transcriber, 'last_confidence', 0.0)
                self._debug_data["whisper_model"] = getattr(self.transcriber, 'model_size', '')
                self._debug_data["initial_prompt"] = initial_prompt or ""
```

After comma spam clean (line 114):
```python
            if self.debug_enabled:
                self._debug_data["after_comma_clean"] = text
                self._debug_data["comma_spam_triggered"] = (text != original) if text else False
```

After spoken punctuation (line 123):
```python
            if self.debug_enabled:
                self._debug_data["spoken_punctuation_applied"] = (text != original) if text else False
                self._debug_data["after_text_cleanup"] = text
```

After post-processing (line 145):
```python
            if self.debug_enabled:
                self._debug_data["pp_input"] = original_before_pp  # capture before pp call
                self._debug_data["pp_output"] = text
                self._debug_data["pp_system_prompt_type"] = (
                    self.ocr_context.app_type.value if self.ocr_context else ""
                )
```

Change the finished signal to include debug data — or add a new signal. The simplest way: add a `debug_data` signal:

```python
    debug_info = Signal(dict)  # Emits debug data collected during run
```

At the end of `run()`, before `self.finished.emit(text, confidence)`:
```python
            if self.debug_enabled:
                self.debug_info.emit(self._debug_data)
```

**Step 7: Handle debug data in `on_transcription_complete`**

Add a new method `_on_debug_info(self, data)` connected to the worker's `debug_info` signal:

```python
    def _on_debug_info(self, data):
        """Process debug data from transcription worker."""
        if not self.debug_manager:
            return

        # Record transcription
        self.debug_manager.start_step()  # Reset timer (already elapsed)
        self.debug_manager.record_transcription(
            model=data.get("whisper_model", ""),
            raw_output=data.get("whisper_raw", ""),
            confidence=data.get("whisper_confidence", 0.0),
            initial_prompt=data.get("initial_prompt", ""),
        )

        # Record text cleanup
        self.debug_manager.record_text_cleanup(
            input_text=data.get("whisper_raw", ""),
            output_text=data.get("after_text_cleanup", ""),
            comma_spam_triggered=data.get("comma_spam_triggered", False),
            spoken_punctuation_applied=data.get("spoken_punctuation_applied", False),
        )

        # Record post-processing
        if data.get("pp_output") is not None:
            self.debug_manager.record_post_processing(
                input_text=data.get("pp_input", ""),
                output_text=data.get("pp_output", ""),
                system_prompt_type=data.get("pp_system_prompt_type", ""),
            )
        elif self.debug_panel:
            self.debug_panel.on_post_processing_skipped()
```

Connect this signal in `start_transcription()`:
```python
        if self.debug_manager:
            self.transcription_worker.debug_info.connect(self._on_debug_info)
```

**Step 8: Finish session in `on_transcription_complete`**

At the end of `on_transcription_complete()`, after dictionary application and before typing (around line 500), add:

```python
            if self.debug_manager:
                self.debug_manager.record_dictionary(
                    replacements_applied={} if text == original else {"original": original, "replaced": text},
                    output_text=text,
                )
```

After typing completes (after `success = self.keyboard_typer.type_text(text)`), add:

```python
                if self.debug_manager:
                    method = "clipboard" if self.keyboard_typer.use_clipboard else "typing"
                    self.debug_manager.record_delivery(method, len(text))
                    self.debug_manager.finish_session(text)
```

Also handle empty text case — after `self.overlay.show_no_speech()` (line 541):

```python
                if self.debug_manager:
                    self.debug_manager.finish_session("")
```

**Step 9: Commit**

```bash
git add src/main.py
git commit -m "feat: wire DebugManager into transcription pipeline"
```

---

### Task 6: Test the full debug flow

**Step 1: Enable debug mode in settings**

1. Run the app
2. Open Settings → scroll to Debug section
3. Check "Enable Debug Mode"
4. Check "Log Full Pipeline Data"
5. Check "Live Debug Panel"
6. Save

**Step 2: Test session logging**

1. Record a transcription using the hotkey
2. Check `.resonance/debug/sessions/` for a new JSON file
3. Verify the JSON contains all pipeline steps with populated data

**Step 3: Test live debug panel**

1. With debug panel enabled, record a transcription
2. Verify the dark panel appears in the bottom-right corner
3. Verify it fills in live as each step completes
4. Verify it auto-dismisses after 15 seconds
5. Verify the X button closes it early

**Step 4: Test HTML report**

1. After a few transcriptions, open Settings → Debug
2. Click "Open Comparison Report"
3. Verify the HTML opens in browser with a table of sessions
4. Check confidence color coding (green/yellow/red)

**Step 5: Test toggle states**

1. Debug Mode OFF → verify sub-options are hidden
2. Debug Mode ON, Logging OFF → verify panel works without saving files
3. Debug Mode ON, Logging ON, Panel OFF → verify files saved but no panel
4. Verify "Open Comparison Report" is grayed out when logging is off

**Step 6: Commit everything**

```bash
git add -A
git commit -m "feat: complete debug mode — session logging, live panel, HTML report"
```
