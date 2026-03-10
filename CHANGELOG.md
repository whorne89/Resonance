# Changelog

## v3.6.0 (2026-03-10)

### New Features

- **Smart media pause** — Media pause now detects whether audio is actually playing before sending the play/pause toggle. Previously, pressing the hotkey with nothing playing would *start* music. Windows uses Core Audio peak meter (IAudioMeterInformation), macOS uses CoreAudio device-is-running query, Linux uses playerctl status check. Falls back to pausing on detection failure.
- **Cross-platform PyInstaller builds** — The build spec now works on Windows, Linux, and macOS. SSL DLL bundling is Windows-only guarded, pynput hidden imports are platform-conditional (_win32/_darwin/_xorg), and dead Tesseract bundling code has been removed.
- **Platform-aware auto-updater** — Update checker now selects the correct release asset per platform (e.g. `Resonance-windows.zip`, `Resonance-linux.tar.gz`, `Resonance-macos.zip`) instead of grabbing the first `.zip`. Supports `.tar.gz` extraction for Linux (preserves Unix execute permissions). Download filenames are preserved from the URL.
- **GitHub Actions CI** — New workflow (`.github/workflows/build.yml`) builds bundled executables on all 3 platforms when a version tag is pushed. Creates a draft GitHub Release with `Resonance-windows.zip`, `Resonance-linux.tar.gz`, and `Resonance-macos.zip` attached.

## v3.5.0 (2026-03-10)

### New Features

- **Source auto-update** — Source installs (git repos) now auto-update via git pull + uv sync instead of just showing "Run: git pull && uv sync". Update toast and Settings both show a changelog dialog, then run the update with a progress dialog showing each step (fetch, pull, sync), and automatically restart the app on success.
- **macOS Accessibility permission check** — On first launch on macOS, if Accessibility permission is not granted, a dialog explains why it's needed and offers to open System Settings. The prompt only shows once per install.
- **One-command installer** — New `install.sh` script for macOS and Linux. Installs git, uv, Tesseract OCR, clones the repo, runs `uv sync`, and creates a launcher (`.command` on macOS, `.desktop` entry on Linux). Run via: `curl -LsSf https://raw.githubusercontent.com/whorne89/Resonance/main/install.sh | bash`
- **Testing checklist** — New `TESTING.md` with step-by-step verification checklist for contributors covering setup, transcription, sound effects, OCR, auto-update, media pause, settings, and edge cases.

### Bug Fixes

- **Hint text cut off on processing overlay** — The "First use may take longer while the model loads" hint badge was clipped to the 200px pill width. The overlay now dynamically widens to fit the hint text, with the pill and badges centered within the wider widget.

## v3.4.0 (2026-03-09)

### New Features

- **First-run model loading hint** — Startup toast now shows "First use may take longer while the model loads" on every launch, since the first transcription after each restart is always slower due to model loading into memory.
- **Application window icon** — Settings, About, and other dialogs now show the Resonance icon in the taskbar and title bar instead of the default Python icon.
- **Pause media during recording** — New toggle in Audio Settings (on by default) that sends a media play/pause key when recording starts and resumes playback when recording stops (on hotkey release). Prevents background music from interfering with voice capture. Uses native Windows API (keybd_event) for reliable media key simulation, with pynput fallback on Linux/macOS.
- **Cross-platform auto-updater** — The auto-update apply step now works on Linux and macOS (bundled installs), not just Windows. Uses a platform-native shell script to wait for process exit, copy new files, and relaunch.

## v3.3.2 (2026-03-09)

### Bug Fixes

- **OCR hallucination guard 0/0 bug** — Punctuation-only transcriptions (e.g. `"... ... ..."`) were silently discarded because stripping periods/commas produced an empty word list, and `0 == 0` passed the "all words are OCR nouns" check. Added `len(words) > 0` guard so empty word lists are no longer treated as hallucinations.
- **Filler word filter too aggressive** — Single-word legitimate inputs like "You", "Oh", "Okay", "Well" were being deleted because the filler set included common real words. Trimmed the filler set to actual fillers only (um, uh, hmm, ah, basically, yeah) and added a minimum of 2 words before the filter activates — single-word inputs are never filtered.
- **Dictionary fuzzy matcher eating adjacent words** — Multi-word sliding windows in fuzzy matching could absorb neighboring words (e.g. "on Claude" fuzzy-matching to "Claude", deleting "on"). Restricted fuzzy matching to single-word windows only. Multi-word exact matching is unaffected.
- **Rephrasing guard rejecting valid grammar fixes** — The post-processing guard that catches LLM rephrasing was rejecting legitimate inflection corrections (e.g. "suggesting" → "suggest") because the corrected form wasn't in the original word set. Added basic stemming so words sharing the same root are recognized as equivalent.

## v3.3.1 (2026-03-07)

### Bug Fixes

- **App crash from Unicode window titles** — The log file handler used Windows' cp1252 encoding by default, which can't encode Unicode characters like `✳` or `⠐` found in window titles (e.g. Claude Code's terminal title). This caused `UnicodeEncodeError` in the file handler's `stream.write()`, silently breaking the transcription pipeline and causing hangs or crashes. Fixed by setting `encoding='utf-8'` on the `RotatingFileHandler` and `errors='replace'` on the console handler.
- **No-console batch file not launching** — `Start Resonance (Windows).bat` used `start /B` which attaches the process to the parent console. When the batch file's `exit` closed the console, the Resonance process was killed. Fixed by using `start ""` with `pythonw.exe` directly from the venv, which creates an independent process that survives the batch file closing.

## v3.3.0 (2026-03-06)

### New Features

- **Cross-platform support (Linux & macOS)** — Resonance now runs on Linux and macOS in addition to Windows. Platform-conditional dependencies install the right packages per OS: winocr on Windows, Tesseract OCR + pywinctl on Linux/macOS. Sound effects use QSoundEffect (PySide6 QtMultimedia) instead of winsound. Post-processor downloads the correct llama-server binary per platform. Audio recorder cascades sample rates for devices that don't support 16kHz. Keyboard paste uses Cmd+V on macOS.

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
