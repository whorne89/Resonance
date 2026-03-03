# Debug Mode Design

## Overview
A Debug section in Settings with tools to capture pipeline data, view live transcription progress, and generate comparison reports. Primarily for development and tuning — not enabled by default.

## Settings UI

```
Debug
  [x] Enable Debug Mode
      Master toggle — gates everything below

  [x] Log Full Pipeline Data
      Saves detailed session data for every transcription
      (requires Debug Mode)

  [x] Live Debug Panel
      Shows real-time pipeline info during transcription
      (requires Debug Mode)

  [Open Comparison Report]
      Generates HTML report from logged sessions, opens in browser
      (requires Log Full Pipeline Data — grayed out otherwise)
```

Toggle states:
- Debug Mode OFF → all sub-options hidden/disabled
- Debug Mode ON, Logging ON, Panel OFF → silent data capture
- Debug Mode ON, Logging OFF, Panel ON → visual only, nothing saved
- Debug Mode ON, both ON → full experience

## Feature 1: Session Logging

### Config keys
```json
{
  "debug": {
    "enabled": false,
    "logging_enabled": false,
    "live_panel_enabled": false
  }
}
```

### Session data model
Each transcription saves a JSON file to `.resonance/debug/sessions/`.

```json
{
  "session_id": "a1b2c3d4",
  "timestamp": "2026-03-02T14:30:22",
  "audio": {
    "duration_seconds": 3.2,
    "avg_rms": 0.045,
    "sample_rate": 16000
  },
  "timing": {
    "ocr_ms": 56,
    "transcription_ms": 2100,
    "post_processing_ms": 850,
    "total_ms": 3200
  },
  "ocr": {
    "enabled": true,
    "app_type": "chat",
    "window_title": "Discord - #general",
    "proper_nouns": ["Steve", "Martin"],
    "raw_text_length": 1240
  },
  "whisper": {
    "model": "small",
    "raw_output": "um yeah i'll be there in like 10 minutes",
    "confidence": 0.87,
    "initial_prompt": "A conversation mentioning Steve and Martin."
  },
  "post_processing": {
    "enabled": true,
    "input": "um yeah i'll be there in like 10 minutes",
    "output": "yeah I'll be there in like 10 minutes",
    "system_prompt_type": "chat"
  },
  "text_cleanup": {
    "input": "yeah I'll be there in like 10 minutes",
    "output": "yeah I'll be there in like 10 minutes",
    "comma_spam_triggered": false,
    "spoken_punctuation_applied": false
  },
  "dictionary": {
    "replacements_applied": {},
    "output": "yeah I'll be there in like 10 minutes"
  },
  "final_text": "yeah I'll be there in like 10 minutes",
  "delivery": {
    "method": "clipboard",
    "char_count": 42
  },
  "learning": {
    "enabled": true,
    "app_key": "discord",
    "vocabulary_injected": ["Steve", "Martin"],
    "style_suffix": "Use casual, conversational style."
  }
}
```

### Storage
- Path: `.resonance/debug/sessions/`
- Filename: `session_YYYY-MM-DD_HHMMSS_{session_id}.json`
- Max storage cap with auto-cleanup (oldest first) to prevent unbounded growth

## Feature 2: Live Debug Panel

### Visual design
- Dark semi-transparent panel in bottom-right corner (same position/style as startup toast)
- Wider and taller than startup toast to fit pipeline info
- X button in top-right corner to close early
- Auto-dismisses after 15 seconds
- Gets replaced if a new transcription starts

### Content (fills in live as each step completes)

```
DEBUG
─────────────────────────────
Recording... ●  RMS: 0.045
Duration: 3.2s

OCR ✓ (56ms)
  App: Discord (#general)
  Type: CHAT
  Names: Steve, Martin

Whisper ✓ (1.2s)
  "um yeah i'll be there in like 10 minutes"
  Confidence: 87%  |  Model: small

Post-Processing ✓ (0.8s)
  In:  "um yeah i'll be there in like 10 minutes"
  Out: "yeah I'll be there in like 10 minutes"

Text Cleanup ✓
  No changes

Dictionary ✓
  No replacements

Final: "yeah I'll be there in like 10 minutes"
Total: 3.2s
```

### Behavior
- Appears on hotkey press (recording starts)
- Each section appears/updates as that pipeline step completes
- Steps not yet complete show as pending (e.g. "Whisper ..." with spinner)
- Steps that are disabled show as "Skipped" (e.g. "Post-Processing: OFF")
- 15 second auto-dismiss timer starts after final text is delivered
- X button always visible to dismiss early
- NOT click-through — user can interact with X button (same as UpdateToast pattern)

### Implementation
- New widget: `DebugPanel` in `src/gui/debug_panel.py`
- Similar architecture to `UpdateToast` (interactive, not click-through)
- VTTApplication emits signals at each pipeline step → DebugPanel updates
- Panel only created/shown when debug mode + live panel are both enabled

## Feature 3: HTML Comparison Report

### Trigger
- Button "Open Comparison Report" in Settings > Debug section
- Grayed out if logging is not enabled
- Generates HTML file at `.resonance/debug/comparison_report.html`
- Opens in default browser via `webbrowser.open()`

### Content
- Table with columns: Timestamp, App Type, Whisper Raw, Post-Processed, Final Text, Confidence
- Each row is one session from the log files
- Most recent sessions at the top
- Color coding: green for high confidence (>85%), yellow for medium (70-85%), red for low (<70%)
- Shows last 100 sessions max

### Implementation
- New module: `src/core/debug_manager.py` — handles session logging, report generation
- HTML generated from session JSON files using string templating (no extra dependencies)

## Architecture

### New files
- `src/core/debug_manager.py` — DebugManager class: session logging, report generation
- `src/gui/debug_panel.py` — DebugPanel widget: live pipeline view

### Modified files
- `src/utils/config.py` — add debug config section + getters/setters
- `src/gui/settings_dialog.py` — add Debug section with toggles + report button
- `src/main.py` — wire DebugManager into pipeline, emit signals for debug panel

### Data flow
1. VTTApplication creates DebugManager on startup (if debug enabled)
2. At each pipeline step, VTTApplication calls DebugManager methods to record data
3. DebugManager holds current session in memory, writes to disk on completion (if logging enabled)
4. DebugManager also emits Qt signals that DebugPanel listens to (if panel enabled)
5. On "Open Comparison Report", DebugManager reads session files and generates HTML

## Future Ideas (Backburner)

### Ctrl+Z Feedback Flow
- Detect when user undoes a Resonance transcription
- Show countdown pill: "Bad result? Hold [hotkey] to describe what went wrong"
- User speaks feedback → transcribed → saved alongside flagged session
- **Why backburnered**: No automatic way to act on feedback. Would need a local LLM or rule engine to close the loop. Session logging alone gives 90% of the value.
- **Revisit when**: We have a system that can learn from user feedback automatically
