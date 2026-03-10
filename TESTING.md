# Resonance — Testing Checklist

Use this checklist to verify Resonance works correctly on your platform. Check off each item as you go.

---

## 1. Setup

- [ ] Fresh clone: `git clone https://github.com/whorne89/Resonance.git && cd Resonance`
- [ ] Install dependencies: `uv sync`
- [ ] Launch: `uv run python src/main.py`
- [ ] App appears in system tray
- [ ] Startup toast shows hotkey, model, and feature status
- [ ] No errors in `.resonance/resonance.log`

## 2. Basic Transcription

- [ ] Hold the hotkey (default: Right Ctrl) and speak
- [ ] Recording overlay appears at bottom-center with red dot + waveform
- [ ] Release hotkey — overlay transitions to processing (blue dots)
- [ ] Transcribed text is typed into the active window
- [ ] Overlay shows "Typing" or "Text Entered" then fades out

## 3. Sound Effects

- [ ] Start tone plays when hotkey is pressed
- [ ] Stop tone plays when hotkey is released
- [ ] Custom sounds: drop `start.wav`/`stop.wav` in `.resonance/sounds/` and verify they're used

## 4. OCR / Post-Processing

- [ ] Enable post-processing in Settings
- [ ] Enable OCR (On-Screen Recognition) in Settings
- [ ] Record in a chat app (Discord, Slack, etc.)
- [ ] Overlay badge shows app type or app name during recording
- [ ] Post-processing fixes grammar and punctuation without changing your words
- [ ] Try in different app types: email client, code editor, terminal

## 5. Auto-Update (Source Install)

- [ ] Open Settings > Updates > click "Check for Updates"
- [ ] If an update is available:
  - [ ] Status shows "Resonance X.Y.Z is available!"
  - [ ] "Update and Restart" button appears
  - [ ] Click it — changelog dialog shows release notes
  - [ ] Click "Proceed with Update" — progress dialog shows git pull + uv sync steps
  - [ ] App restarts automatically with the new version
- [ ] If up to date: status shows "Up to date!"
- [ ] Auto-update toast: wait 8 seconds after startup (or launch with an older version)
  - [ ] Toast appears with update prompt
  - [ ] Click "Yes" — changelog → update → restart flow works

## 6. Media Pause

- [ ] Play music or audio in a media player
- [ ] Enable "Pause media during recording" in Settings > Audio
- [ ] Press hotkey — media should pause
- [ ] Release hotkey — media should resume after transcription completes

## 7. First-Run Hint

- [ ] On first launch (or after clearing settings), start a recording and release
- [ ] During processing, a hint badge shows below the blue dots: "First use may take longer while the model loads"
- [ ] The hint text is fully visible (not cut off)
- [ ] The hint appears centered below the overlay pill
- [ ] Hint does not appear on subsequent recordings in the same session

## 8. Settings

- [ ] Open Settings from tray icon
- [ ] Change hotkey — new hotkey works after closing Settings
- [ ] Change Whisper model — new model downloads and works
- [ ] Change audio device — recording uses the selected device
- [ ] Toggle typing method (character-by-character vs clipboard paste)
- [ ] Open dictionary editor — add/remove entries, verify they apply to transcription
- [ ] All toggles save and persist across restarts

## 9. Edge Cases

- [ ] **No microphone**: App starts, shows error when trying to record
- [ ] **No internet**: App starts normally, update check fails gracefully
- [ ] **Tesseract missing** (Linux/macOS): OCR gracefully falls back, transcription still works
- [ ] **Long recording** (30+ seconds): Audio captured correctly, transcription completes
- [ ] **Empty recording** (press and release immediately): "No speech detected" message, no crash
- [ ] **Rapid press/release**: No crash or double-recording

---

## Platform-Specific

### Linux
- [ ] Sound effects play (via Qt multimedia, not winsound)
- [ ] System tray icon shows correctly
- [ ] `.desktop` entry launches the app from application menu

### macOS
- [ ] Accessibility permission prompt appears on first launch
- [ ] After granting Accessibility permission, hotkeys work
- [ ] Cmd+V paste works for clipboard typing method

---

## Reporting Issues

If any check fails:
1. Note the step number and what happened
2. Copy the relevant log from `.resonance/resonance.log`
3. Include your OS, distro (Linux), and Python version
4. Open an issue at https://github.com/whorne89/Resonance/issues
