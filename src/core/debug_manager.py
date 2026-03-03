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

            app_type = s.get("ocr", {}).get("app_type", "\u2014")
            whisper_raw = s.get("whisper", {}).get("raw_output", "\u2014")
            pp_output = s.get("post_processing", {}).get("output", "\u2014")
            if not s.get("post_processing", {}).get("enabled"):
                pp_output = "<em>OFF</em>"
            final = s.get("final_text", "\u2014")
            ts = s.get("timestamp", "\u2014")
            timing = s.get("timing", {})
            total = timing.get("total_ms", "\u2014")

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
