# OCR Screen Context Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add screen context awareness via OCR that captures the active window on hotkey press, feeds proper nouns to Whisper as vocabulary hints, and selects app-type-specific post-processor prompts.

**Architecture:** New `ScreenContextEngine` module runs OCR in a background thread on hotkey press (~56ms total). Results feed into Whisper `initial_prompt` (name accuracy) and post-processor system prompt (app-type formatting). Python code handles structural formatting (chat trailing period removal, email greetings).

**Tech Stack:** winocr (Windows native OCR), mss (screenshot capture), win32gui (window info), existing faster-whisper + llama-server

---

### Task 1: Add dependencies

**Files:**
- Modify: `pyproject.toml:15-21` (dependencies list)

**Step 1: Add winocr and mss to pyproject.toml**

Add `"winocr>=0.0.8"` and `"mss>=9.0.0"` to the dependencies list in pyproject.toml.

**Step 2: Sync dependencies**

Run: `uv sync`

**Step 3: Commit**

```
git add pyproject.toml uv.lock
git commit -m "deps: add winocr and mss for OCR screen context"
```

---

### Task 2: Create screen_context.py module

**Files:**
- Create: `src/core/screen_context.py`

The module contains:
- `AppType` enum (CHAT, EMAIL, CODE, DOCUMENT, GENERAL)
- `ScreenContext` dataclass (raw_text, app_type, proper_nouns, window_title)
- `ScreenContextEngine` class with:
  - `capture()` — full pipeline: screenshot → OCR → detect app → extract nouns → return ScreenContext
  - `_get_foreground_window()` — returns (title, rect) via win32gui ctypes
  - `_capture_window(rect)` — captures window region via mss, returns PIL Image
  - `_extract_text(image)` — runs winocr on image, returns str
  - `_detect_app_type(ocr_text, window_title)` — heuristic keyword matching
  - `_extract_proper_nouns(ocr_text)` — capitalized words minus common UI words
  - `build_whisper_prompt(proper_nouns, app_type)` — natural sentence for initial_prompt
  - `build_system_prompt(app_type, proper_nouns)` — returns full system prompt for the app type
  - `apply_chat_formatting(text)` — strips trailing period for CHAT mode
  - `apply_email_structure(text, context)` — adds greeting if recipient detected

All prompts (CHAT_SYSTEM_PROMPT, EMAIL_SYSTEM_PROMPT, CODE_SYSTEM_PROMPT, DOCUMENT_SYSTEM_PROMPT) are defined as module-level constants. The existing SYSTEM_PROMPT is imported from post_processor.py for GENERAL mode.

Graceful fallback: if OCR fails for any reason (winocr not available, no language pack, exception), `capture()` returns None and the caller proceeds without context.

**Step 2: Commit**

```
git add src/core/screen_context.py
git commit -m "feat: add screen context engine with OCR and app detection"
```

---

### Task 3: Add OCR config setting

**Files:**
- Modify: `src/utils/config.py:296-298` (after set_post_processing_enabled)

Add two methods following the exact pattern of get/set_post_processing_enabled:
- `get_ocr_enabled()` — returns `self.get("ocr", "enabled", default=False)`
- `set_ocr_enabled(enabled)` — calls `self.set("ocr", "enabled", value=enabled)`

**Step 2: Commit**

```
git add src/utils/config.py
git commit -m "feat: add OCR enabled config setting"
```

---

### Task 4: Modify Transcriber to accept initial_prompt

**Files:**
- Modify: `src/core/transcriber.py:95-129` (transcribe method)

Add an optional `initial_prompt=None` parameter to `transcribe()`. Pass it through to `self.model.transcribe()` only if not None/empty.

Change at line 115-120:
```python
segments, info = self.model.transcribe(
    audio_data,
    language=language,
    beam_size=5,
    vad_filter=False,
    initial_prompt=initial_prompt or None,
)
```

**Step 2: Commit**

```
git add src/core/transcriber.py
git commit -m "feat: add initial_prompt parameter to transcriber"
```

---

### Task 5: Modify PostProcessor to accept custom system prompt

**Files:**
- Modify: `src/core/post_processor.py:116-145` (process method)
- Modify: `src/core/post_processor.py:269-278` (_process_via_api method)

Add `system_prompt=None` parameter to `process()` and `_process_via_api()`. If provided, use it instead of the module-level SYSTEM_PROMPT.

In `process()` at line 142:
```python
return self._process_via_api(raw_text, system_prompt=system_prompt)
```

In `_process_via_api()` at line 273:
```python
{"role": "system", "content": system_prompt or SYSTEM_PROMPT},
```

**Step 2: Commit**

```
git add src/core/post_processor.py
git commit -m "feat: allow custom system prompt in post-processor"
```

---

### Task 6: Integrate OCR into main.py pipeline

**Files:**
- Modify: `src/main.py`

Changes needed:

1. **Import** ScreenContextEngine at top (line ~28):
   ```python
   from core.screen_context import ScreenContextEngine
   ```

2. **Initialize** in VTTApplication.__init__ (after line 125):
   ```python
   self.screen_context = None
   if self.config.get_ocr_enabled():
       self.screen_context = ScreenContextEngine()
   self._current_ocr_context = None
   ```

3. **on_hotkey_press** (line 167-186): After starting recording (line 175), fire OCR in background thread:
   ```python
   # Fire OCR capture in background (non-blocking)
   if self.screen_context:
       import threading
       def _capture_ocr():
           try:
               self._current_ocr_context = self.screen_context.capture()
           except Exception as e:
               self.logger.warning(f"OCR capture failed: {e}")
               self._current_ocr_context = None
       threading.Thread(target=_capture_ocr, daemon=True).start()
   else:
       self._current_ocr_context = None
   ```

4. **TranscriptionWorker** (line 38-71): Add `ocr_context` parameter. Use it to build initial_prompt and system_prompt:
   ```python
   def __init__(self, transcriber, audio_data, post_processor=None, logger=None, ocr_context=None):
       ...
       self.ocr_context = ocr_context

   def run(self):
       initial_prompt = None
       system_prompt = None
       if self.ocr_context:
           from core.screen_context import ScreenContextEngine
           initial_prompt = ScreenContextEngine.build_whisper_prompt(
               self.ocr_context.proper_nouns, self.ocr_context.app_type
           )
           system_prompt = ScreenContextEngine.build_system_prompt(
               self.ocr_context.app_type, self.ocr_context.proper_nouns
           )

       text = self.transcriber.transcribe(self.audio_data, initial_prompt=initial_prompt)

       if text and self.post_processor:
           text = self.post_processor.process(text, system_prompt=system_prompt)

       # Apply structural formatting
       if self.ocr_context:
           from core.screen_context import AppType, ScreenContextEngine
           if self.ocr_context.app_type == AppType.CHAT:
               text = ScreenContextEngine.apply_chat_formatting(text)
           elif self.ocr_context.app_type == AppType.EMAIL:
               text = ScreenContextEngine.apply_email_structure(text, self.ocr_context)

       self.finished.emit(text)
   ```

5. **start_transcription** (line 260-263): Pass OCR context to worker:
   ```python
   self.transcription_worker = TranscriptionWorker(
       self.transcriber, audio_data, self.post_processor, self.logger,
       ocr_context=self._current_ocr_context
   )
   ```

6. **on_settings_changed** — reload screen_context when settings change (same pattern as post_processor reload).

**Step 2: Commit**

```
git add src/main.py
git commit -m "feat: integrate OCR screen context into transcription pipeline"
```

---

### Task 7: Add OCR toggle to settings dialog

**Files:**
- Modify: `src/gui/settings_dialog.py`

Add OCR checkbox to the Speech Recognition group (after post-processing checkbox, ~line 644):
```python
# OCR screen context checkbox + description
self.ocr_cb = QCheckBox("Screen Context (OCR)")
ocr_desc = QLabel(
    "Captures the active window to improve name accuracy\n"
    "and adapt formatting for chat, email, code, and documents.\n"
    "Requires Post-Processing to be enabled."
)
ocr_desc.setStyleSheet("color: rgba(255, 255, 255, 140); font-size: 11px;")

ocr_col = QVBoxLayout()
ocr_col.setSpacing(2)
ocr_col.addWidget(self.ocr_cb)
ocr_col.addWidget(ocr_desc)
layout.addRow("", ocr_col)
```

Also:
- In `load_current_settings()`: load OCR state, disable checkbox if PP is off
- In `save_settings()`: save OCR state, detect changes
- Connect post_processing_cb stateChanged to enable/disable ocr_cb:
  ```python
  self.post_processing_cb.stateChanged.connect(self._on_pp_toggled)

  def _on_pp_toggled(self, state):
      if not self.post_processing_cb.isChecked():
          self.ocr_cb.setChecked(False)
          self.ocr_cb.setEnabled(False)
      else:
          self.ocr_cb.setEnabled(True)
  ```

**Step 2: Commit**

```
git add src/gui/settings_dialog.py
git commit -m "feat: add OCR screen context toggle to settings"
```

---

### Task 8: Add OCR badge to recording overlay

**Files:**
- Modify: `src/gui/recording_overlay.py` (badge list)
- Modify: `src/main.py` (pass OCR state to overlay)

Follow the existing pattern for the "Post-Processing: ON" badge. Add "Screen Context: ON" badge when OCR is enabled.

**Step 2: Commit**

```
git add src/gui/recording_overlay.py src/main.py
git commit -m "feat: show Screen Context badge on recording overlay"
```

---

### Task 9: Update startup toast with OCR status

**Files:**
- Modify: `src/main.py` (startup toast construction)

Add OCR status line to the startup toast details, following the existing pattern for post-processing status.

**Step 2: Commit**

```
git add src/main.py
git commit -m "feat: show OCR status in startup toast"
```

---

### Task 10: Update documentation

**Files:**
- Modify: `README.md` (features, configuration, changelog)
- Modify: `CLAUDE.md` (architecture, transcription flow)

**Step 2: Commit and push**

```
git add README.md CLAUDE.md
git commit -m "docs: add OCR screen context to README and CLAUDE.md"
git push origin main
```
