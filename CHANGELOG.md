# Changelog

## v3.2.0 (2026-03-03)

### New Features

- **Debug Mode** — New Debug section in Settings with three sub-features:
  - **Session Logging** — Saves detailed JSON data for every transcription session to `.resonance/debug/sessions/`. Captures audio stats, OCR results, Whisper output, post-processing, text cleanup, dictionary replacements, learning engine data, delivery method, and full timing breakdown. Auto-cleanup keeps max 500 sessions.
  - **Live Debug Panel** — Dark overlay anchored to bottom-right corner shows real-time pipeline progress during transcription. Each step fills in live as it completes: Recording, OCR, Whisper, Post-Processing, Text Cleanup, Dictionary, Learning, and Result. Shows timing per step in seconds and milliseconds. Auto-dismisses after 25 seconds. X button to close early.
  - **HTML Comparison Report** — Generates a styled dark-theme HTML report from logged sessions with columns for timestamp, duration, app type, app name, Whisper raw output, post-processed text, text cleanup, dictionary replacements, final text, confidence (color-coded), model, timing breakdown, delivery method, OCR names, and learning data. Includes CSV export for external analysis. Opens in default browser from Settings.
- **Learning Engine in Debug Pipeline** — Debug panel shows per-app learning data: app key, session count, confidence, vocabulary injected, style metrics (formality, punctuation, capitalization, abbreviations), and prompt suffix.

### Bug Fixes

- **False "no speech detected" during recording** — Fixed spurious key release events from pynput causing a false release-then-repress cycle mid-recording. Added 100ms debounce timer to hotkey release events in HotkeyManager. Added defense-in-depth guard in on_hotkey_press to ignore if already recording. Added stale transcription completion guard — if a previous transcription finishes while a new recording is active, UI updates (overlay, tray) are suppressed to prevent the "no speech detected" toast from appearing over an active recording.
- **Whisper timing showing 0ms in debug panel** — Timing was being measured on the main thread after the worker finished, instead of inside the worker where the actual processing happens. Moved timing capture into TranscriptionWorker for both Whisper and post-processing steps.

### Improvements

- Debug panel height is now dynamic based on screen size instead of a fixed 800px cap — long pipeline outputs no longer get cut off.
- All timing displays in the debug panel use consistent "Xs (Yms)" format (e.g., "2.1s (2100ms)").
- Result section shows total time in the label with checkmark, consistent with all other pipeline steps.
- Close button (X) on debug panel is custom-painted for reliable rendering with orange hover highlight.

## v3.1.6 (2026-03-02)

- Fix auto-update infinite loop — clean old dist-info before xcopy
- Fix auto-update batch script not executing + relay signals
- Fix relay worker signals through QObject for main-thread dispatch

## v3.1.5 (2026-02-28)

- Fix post-download startup toast not showing
- Fix update toast not showing + settings crash + question hallucination guard

## v3.1.4 (2026-02-26)

- Self-learning recognition engine — per-app vocabulary and style profiles
- Recording overlay with feature badges and accuracy display
- OSR (On-Screen Recognition) with app-type detection
- Post-processing with Qwen 2.5 1.5B via llama-server
- Custom dictionary with fuzzy matching
- Auto-updater via GitHub Releases
