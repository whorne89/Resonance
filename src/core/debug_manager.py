"""
Debug manager for Resonance.
Handles session logging, pipeline step recording, and HTML report generation.
Emits Qt signals for the live debug panel to consume.
"""

import csv
import html as html_mod
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
    recording_stopped = Signal(dict)    # {"duration_seconds": ..., "sample_rate": ...}
    ocr_completed = Signal(dict)        # {"app_type": ..., "proper_nouns": ..., "timing_ms": ...}
    transcription_completed = Signal(dict)  # {"raw_output": ..., "confidence": ..., "timing_ms": ...}
    post_processing_completed = Signal(dict)  # {"input": ..., "output": ..., "timing_ms": ...}
    text_cleanup_completed = Signal(dict)    # {"input": ..., "output": ..., "comma_spam": ..., "spoken_punct": ...}
    dictionary_completed = Signal(dict)      # {"replacements_applied": ..., "output": ...}
    learning_completed = Signal(dict)        # {"app_key": ..., "style_metrics": ..., "style_suffix": ...}
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

        if self._live_panel_enabled:
            self.recording_stopped.emit({
                "duration_seconds": round(duration_seconds, 2),
                "sample_rate": sample_rate,
            })

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

    def record_transcription(self, model, raw_output, confidence, initial_prompt, timing_ms=None):
        """Record Whisper transcription results."""
        if not self._current_session:
            return
        elapsed = timing_ms if timing_ms is not None else self._elapsed_ms()
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

    def record_post_processing(self, input_text, output_text, system_prompt_type, timing_ms=None):
        """Record post-processing results."""
        if not self._current_session:
            return
        elapsed = timing_ms if timing_ms is not None else self._elapsed_ms()
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

    def record_learning(self, enabled, app_key, vocabulary_injected, style_suffix,
                        style_metrics=None, sessions_count=0, confidence=0.0):
        """Record learning engine data."""
        if not self._current_session:
            return
        learning_data = {
            "enabled": enabled,
            "app_key": app_key or "",
            "vocabulary_injected": vocabulary_injected or [],
            "style_suffix": style_suffix or "",
            "style_metrics": style_metrics or {},
            "sessions_count": sessions_count,
            "confidence": round(confidence, 2),
        }
        self._current_session["learning"] = learning_data

        if self._live_panel_enabled:
            self.learning_completed.emit(learning_data)

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

    # ── Reports ────────────────────────────────────────────────────

    def generate_report(self):
        """Generate an HTML comparison report and open in browser."""
        sessions = self._load_sessions(limit=100)
        if not sessions:
            self.logger.warning("No debug sessions found for report")
            return False

        report_dir = Path(get_app_data_path("debug"))
        report_dir.mkdir(parents=True, exist_ok=True)

        # Write CSV alongside the HTML
        csv_path = report_dir / "sessions.csv"
        self._write_csv(sessions, csv_path)

        html = self._build_html(sessions, csv_path.name)
        report_path = report_dir / "comparison_report.html"

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

    def _extract_row(self, s):
        """Extract a flat dict of display values from a session."""
        timing = s.get("timing", {})
        audio = s.get("audio", {})
        ocr = s.get("ocr", {})
        whisper = s.get("whisper", {})
        pp = s.get("post_processing", {})
        cleanup = s.get("text_cleanup", {})
        delivery = s.get("delivery", {})
        learning = s.get("learning", {})

        confidence = whisper.get("confidence", 0)
        if confidence > 0.85:
            conf_class = "high"
        elif confidence > 0.70:
            conf_class = "medium"
        else:
            conf_class = "low"

        # Text cleanup details
        cleanup_parts = []
        if cleanup.get("comma_spam_triggered"):
            cleanup_parts.append("Comma spam cleaned")
        if cleanup.get("spoken_punctuation_applied"):
            cleanup_parts.append("Spoken punct applied")
        if not cleanup_parts and cleanup.get("input", "") != cleanup.get("output", ""):
            cleanup_parts.append("Text modified")
        cleanup_str = ", ".join(cleanup_parts) if cleanup_parts else "No changes"

        # Dictionary replacements
        dict_repl = s.get("dictionary", {}).get("replacements_applied", {})
        dict_str = ", ".join(f"{k}\u2192{v}" for k, v in dict_repl.items()) if dict_repl else ""

        # Learning details
        learning_vocab_list = learning.get("vocabulary_injected", [])
        style = learning.get("style_metrics", {})
        learning_detail_parts = []
        if learning.get("enabled") and learning.get("app_key"):
            sessions_count = learning.get("sessions_count", 0)
            learn_conf = learning.get("confidence", 0)
            learning_detail_parts.append(f'{sessions_count} sessions, {learn_conf:.0%} conf')
            if style.get("sample_count", 0) >= 3:
                learning_detail_parts.append(
                    f'formality {style.get("formality_score", 0):.0%}'
                )
        learning_detail = "; ".join(learning_detail_parts)

        return {
            "timestamp": s.get("timestamp", "\u2014"),
            "duration": f'{audio.get("duration_seconds", 0):.1f}s',
            "duration_raw": audio.get("duration_seconds", 0),
            "model": whisper.get("model", "\u2014"),
            "app_type": ocr.get("app_type", "\u2014") if ocr.get("enabled") else "\u2014",
            "window": ocr.get("window_title", "") if ocr.get("enabled") else "",
            "names": ", ".join(ocr.get("proper_nouns", [])) if ocr.get("enabled") else "",
            "whisper_raw": whisper.get("raw_output", "\u2014"),
            "pp_output": pp.get("output", "\u2014") if pp.get("enabled") else "",
            "pp_enabled": pp.get("enabled", False),
            "cleanup_str": cleanup_str,
            "dict_str": dict_str,
            "final_text": s.get("final_text", "\u2014"),
            "confidence": confidence,
            "conf_class": conf_class,
            "ocr_ms": timing.get("ocr_ms", ""),
            "whisper_ms": timing.get("transcription_ms", ""),
            "pp_ms": timing.get("post_processing_ms", ""),
            "total_ms": timing.get("total_ms", ""),
            "delivery": delivery.get("method", "\u2014"),
            "chars": delivery.get("char_count", ""),
            "learning_app": learning.get("app_key", "") if learning.get("enabled") else "",
            "learning_vocab": len(learning_vocab_list),
            "learning_detail": learning_detail,
        }

    def _write_csv(self, sessions, csv_path):
        """Write session data to CSV for external analysis."""
        fields = [
            "timestamp", "duration", "model", "app_type", "window", "names",
            "whisper_raw", "pp_output", "cleanup_str", "dict_str",
            "final_text", "confidence",
            "ocr_ms", "whisper_ms", "pp_ms", "total_ms",
            "delivery", "chars",
            "learning_app", "learning_vocab", "learning_detail",
        ]
        try:
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
                writer.writeheader()
                for s in sessions:
                    row = self._extract_row(s)
                    writer.writerow(row)
            self.logger.info(f"CSV exported: {csv_path}")
        except Exception as e:
            self.logger.error(f"Failed to write CSV: {e}")

    def _esc(self, text):
        """HTML-escape a string."""
        return html_mod.escape(str(text)) if text else ""

    def _build_html(self, sessions, csv_filename):
        """Build an HTML comparison report from session data."""
        rows = []
        for s in sessions:
            r = self._extract_row(s)

            # Format timing breakdown
            parts = []
            if r["ocr_ms"]:
                parts.append(f'OCR {r["ocr_ms"]}')
            if r["whisper_ms"]:
                parts.append(f'Whisper {r["whisper_ms"]}')
            if r["pp_ms"]:
                parts.append(f'PP {r["pp_ms"]}')
            timing_detail = " / ".join(parts)

            total = r["total_ms"]
            if isinstance(total, (int, float)) and total >= 1000:
                total_str = f'{total / 1000:.1f}s'
            elif total:
                total_str = f'{total}ms'
            else:
                total_str = "\u2014"

            pp_cell = self._esc(r["pp_output"]) if r["pp_enabled"] else '<span class="off">OFF</span>'
            dict_cell = self._esc(r["dict_str"]) if r["dict_str"] else '<span class="off">\u2014</span>'
            learn_cell = self._esc(r["learning_app"]) or '<span class="off">\u2014</span>'
            if r["learning_detail"]:
                learn_cell += f'<br><span class="detail">{self._esc(r["learning_detail"])}</span>'

            rows.append(f"""<tr>
                <td class="ts">{self._esc(r["timestamp"])}</td>
                <td>{self._esc(r["duration"])}</td>
                <td>{self._esc(r["app_type"])}</td>
                <td class="text">{self._esc(r["window"])}</td>
                <td class="text">{self._esc(r["whisper_raw"])}</td>
                <td class="text">{pp_cell}</td>
                <td>{self._esc(r["cleanup_str"])}</td>
                <td>{dict_cell}</td>
                <td class="text final">{self._esc(r["final_text"])}</td>
                <td class="{r["conf_class"]}">{r["confidence"]:.0%}</td>
                <td>{self._esc(r["model"])}</td>
                <td class="timing">{total_str}<br><span class="detail">{timing_detail}</span></td>
                <td>{self._esc(r["delivery"])}</td>
                <td>{self._esc(r["names"])}</td>
                <td>{learn_cell}</td>
            </tr>""")

        rows_html = "\n".join(rows)
        generated = datetime.now().strftime("%Y-%m-%d %H:%M")

        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Resonance Debug Report</title>
<style>
    * {{ box-sizing: border-box; }}
    body {{ font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
           background: #0f0f1e; color: #d0d0d0; margin: 0; padding: 32px; }}

    .header {{ display: flex; align-items: baseline; gap: 16px; margin-bottom: 8px; }}
    h1 {{ color: #3498db; font-size: 28px; margin: 0; }}
    .meta {{ color: #666; font-size: 13px; }}

    .toolbar {{ display: flex; gap: 12px; align-items: center; margin-bottom: 24px; }}
    .btn {{ background: #2d2d4e; color: #c0c0c0; border: 1px solid #3d3d5e;
            padding: 7px 16px; border-radius: 6px; cursor: pointer; font-size: 12px;
            text-decoration: none; }}
    .btn:hover {{ background: #3d3d5e; color: #fff; }}

    table {{ width: 100%; border-collapse: collapse; }}
    thead {{ position: sticky; top: 0; z-index: 1; }}
    th {{ background: #1a1a30; padding: 10px 8px; text-align: left; font-size: 11px;
         font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;
         color: #8888aa; border-bottom: 2px solid #2d2d4e; white-space: nowrap; }}
    td {{ padding: 8px 8px; border-bottom: 1px solid #1a1a30; font-size: 12px;
         vertical-align: top; line-height: 1.4; }}
    tr:hover {{ background: #1a1a35; }}

    .ts {{ white-space: nowrap; font-size: 11px; color: #888; }}
    .text {{ max-width: 280px; word-wrap: break-word; }}
    .final {{ color: #e8e8e8; font-weight: 500; }}
    .timing {{ white-space: nowrap; }}
    .detail {{ font-size: 10px; color: #666; }}

    .high {{ color: #2ecc71; font-weight: 600; }}
    .medium {{ color: #f39c12; font-weight: 600; }}
    .low {{ color: #e74c3c; font-weight: 600; }}
    .off {{ color: #555; font-style: italic; }}
</style>
</head>
<body>

<div class="header">
    <h1>Resonance Debug Report</h1>
    <span class="meta">{len(sessions)} sessions &middot; Generated {generated}</span>
</div>

<div class="toolbar">
    <a class="btn" href="{csv_filename}" download>Export CSV</a>
</div>

<table>
<thead>
    <tr>
        <th>Timestamp</th>
        <th>Duration</th>
        <th>App Type</th>
        <th>App</th>
        <th>Whisper Raw</th>
        <th>Post-Processed</th>
        <th>Text Cleanup</th>
        <th>Dictionary</th>
        <th>Final Text</th>
        <th>Conf.</th>
        <th>Model</th>
        <th>Timing</th>
        <th>Delivery</th>
        <th>OCR Names</th>
        <th>Learning</th>
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
