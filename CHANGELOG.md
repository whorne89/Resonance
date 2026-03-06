# Changelog

## v3.2.3 (2026-03-06)

### Improvements

- **OCR extraction split into Names vs Words** — Proper noun extraction now returns two categories: **Names** (person names from the first-names list + @usernames from chat) and **Words** (useful vocabulary like product/company names). Debug panel and HTML report show both separately. Junk words like "Changelog", "Tightened", "Installed" are now aggressively filtered out.
- **Massively improved OCR word filtering** — Added suffix-based filtering for word endings that never appear in proper nouns (-tion, -ment, -ness, -ful, -less, -ous, -ible, -able, -ize, -ated, -ating, -ology, -ture, -ory). Past tense (-ed), gerund (-ing), adverb (-ly), and agent noun (-er/-or with common root) words are now rejected. Expanded the common English words list from ~240 to ~600+ words covering tech/dev terms. Added -es and -ies plural root detection.

### Bug Fixes

- **Short phrases with names silently discarded** — The prompt hallucination guard was too aggressive (50% threshold), causing legitimate short utterances like "Hey Jordan" to be discarded when the name appeared on screen via OCR. Tightened to only discard when *every* word is an OCR noun (100%), since real hallucinations are pure noun regurgitation while real speech contains non-noun words.
- **Dictionary fuzzy matcher eating adjacent words** — The sliding-window fuzzy matcher was absorbing common words next to dictionary entries (e.g. "to Claude" matched "Claude" at 0.86 similarity, replacing the whole window and deleting "to"). Multi-word windows that already contain the correct word are now skipped.
- **Post-processor rephrasing user's words** — Qwen was silently rewriting sentences (e.g. "you have no idea how much I need this" → "I totally need this") instead of just fixing grammar/punctuation. Tightened the content deletion guard from 40% to 10% — if the model removes more than 10% of text length, the original is returned unchanged. Added a new rephrasing guard that rejects output containing any content word (4+ characters) the speaker never said, with a contraction whitelist so legitimate fixes like "do not" → "don't" still pass.

## v3.2.2 (2026-03-03)

### New Features

- **Changelog dialog before auto-update** — Clicking "Yes" on the update toast now opens a dialog showing the GitHub release notes (rendered as markdown) before downloading. "Cancel" aborts, "Proceed with Update" starts the download. Same dialog appears when clicking "Download and Install" in Settings.

### Improvements

- **Update toast auto-dismiss extended** — Increased from 10 seconds to 25 seconds so users have more time to decide.

## v3.2.1 (2026-03-03)

### New Features

- **Debug Mode** — New Debug section in Settings with three sub-features:
  - **Session Logging** — Saves detailed JSON data for every transcription session to `.resonance/debug/sessions/`. Captures audio stats, OCR results, Whisper output, post-processing, text cleanup, dictionary replacements, learning engine data, delivery method, and full timing breakdown. Auto-cleanup keeps max 500 sessions.
  - **Live Debug Panel** — Dark overlay anchored to bottom-right corner shows real-time pipeline progress during transcription. Each step fills in live as it completes: Recording, OCR, Whisper, Post-Processing, Text Cleanup, Dictionary, Learning, and Result. Shows timing per step in seconds and milliseconds. Auto-dismisses after 25 seconds. X button to close early.
  - **HTML Comparison Report** — Generates a styled dark-theme HTML report from logged sessions with columns for timestamp, duration, app type, app name, Whisper raw output, post-processed text, text cleanup, dictionary replacements, final text, confidence (color-coded), model, timing breakdown, delivery method, OCR names, and learning data. Includes CSV export for external analysis. Opens in default browser from Settings.
- **Learning Engine in Debug Pipeline** — Debug panel shows per-app learning data: app key, session count, confidence, vocabulary injected, style metrics (formality, punctuation, capitalization, abbreviations), and prompt suffix.
- **Name-aware vocabulary** — Added a 250-name first-name list. Names are prioritized first in Whisper hints (surviving the 30-word truncation cap) and bypass frequency requirements in the learning engine.
- **Smart vocabulary frequency bands** — Learned vocabulary now uses three-band filtering: noise (frequency < 3, excluded), contextual (frequency >= 3 and appears in < 80% of sessions, promoted to hints), and static UI (appears in 80%+ of sessions like Slack's "Threads"/"Huddles", auto-demoted). Per-word session tracking added to app profiles.
- **Content deletion guard** — New post-processing guard rejects LLM output that removes more than 40% of the input content (for inputs longer than 30 characters). Logs the deletion percentage for debug sessions.

### Bug Fixes

- **Period-eating regex in text cleaners** — The spoken punctuation collapse regex was treating `.` as a prefix symbol, turning `"Resonance. I'm"` into `"Resonance.I'm"` before the LLM ever saw it. Removed `.` from the symbol character class and added a targeted filename-dot rule that only collapses dot-space before lowercase (e.g. `main. py` → `main.py`), not before uppercase sentence starts.
- **Content deletion in Terminal/Code contexts** — Terminal and Code system prompts were missing the content-preservation rules ("DO NOT remove/shorten/summarize") that already existed in the base, Email, and Document prompts. Qwen was aggressively deleting content — 48% in one observed session.
- **Toxic "Minimal punctuation." style hint** — The learning engine's `build_style_prompt_suffix()` was appending `"Minimal punctuation."` based on OCR style metrics, which Qwen interpreted as "minimize the text" and deleted content. Removed all punctuation hints entirely. Also skip style hints for terminal/code app types since OCR metrics from command output don't reflect the user's dictation style.
- **Hallucinated responses not caught** — Expanded the answer-pattern guard with 15 new imperative/instructional prefixes (`"open your"`, `"type this"`, `"you can"`, `"step 1"`, etc.) that the model uses when it starts answering instead of cleaning.
- **False "no speech detected" during recording** — Fixed spurious key release events from pynput causing a false release-then-repress cycle mid-recording. Added 100ms debounce timer to hotkey release events in HotkeyManager. Added defense-in-depth guard in on_hotkey_press to ignore if already recording. Added stale transcription completion guard — if a previous transcription finishes while a new recording is active, UI updates (overlay, tray) are suppressed to prevent the "no speech detected" toast from appearing over an active recording.
- **Whisper timing showing 0ms in debug panel** — Timing was being measured on the main thread after the worker finished, instead of inside the worker where the actual processing happens. Moved timing capture into TranscriptionWorker for both Whisper and post-processing steps.

### Improvements

- **Proper noun extraction overhaul** — Added a 242-word common English word filter and verb-suffix stripping (-ed, -ing, -s) to stop garbage words like "Worked", "Yeah", "Bashcd", "Entered" from polluting Whisper vocabulary hints. Expanded the UI/terminal word exclusion list. ALL-CAPS words longer than 4 characters are now skipped (headings/acronyms, not names).
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
