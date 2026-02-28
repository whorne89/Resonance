# Post-Processor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Re-add LLM post-processing to clean up Whisper transcription output (grammar, punctuation, capitalization, filler removal) using llama-server + Qwen 2.5 0.5B GGUF.

**Architecture:** PostProcessor class manages a llama-server subprocess on localhost:8787. Lazy-loaded on first `.process()` call. Lifecycle tied to settings checkbox — created when ON, `.shutdown()` kills server when OFF. Runs inside TranscriptionWorker QThread between Whisper output and dictionary replacements.

**Tech Stack:** llama-server (llama.cpp), Qwen 2.5 0.5B Instruct GGUF (q4_k_m, ~400 MB), urllib for HTTP API calls, subprocess for server management.

---

### Task 1: Add config accessors for post-processing

**Files:**
- Modify: `src/utils/config.py:260-290` (after dictionary methods)

**Step 1: Add config methods**

Add these methods to the `ConfigManager` class at the end (after `set_dictionary_fuzzy_threshold`):

```python
def get_post_processing_enabled(self):
    """Get whether post-processing is enabled."""
    return self.get("post_processing", "enabled", default=False)

def set_post_processing_enabled(self, enabled):
    """Set whether post-processing is enabled."""
    self.set("post_processing", "enabled", value=enabled)
```

No default config entry needed — `get()` returns `False` if the key doesn't exist yet, and `set()` creates the path on first save.

**Step 2: Verify**

Run: `python -c "from utils.config import ConfigManager; c = ConfigManager(); print(c.get_post_processing_enabled())"`
Expected: `False`

**Step 3: Commit**

```bash
git add src/utils/config.py
git commit -m "feat: add post-processing config accessors"
```

---

### Task 2: Create PostProcessor class

**Files:**
- Create: `src/core/post_processor.py`

**Step 1: Write the PostProcessor class**

This is a simplified version of the previous implementation — llama-server only, no ONNX, no formatting commands. The system prompt focuses only on grammar, punctuation, capitalization, and filler word removal.

```python
"""
Post-processing module for transcription text cleanup.
Uses a small language model via llama-server to fix grammar,
punctuation, capitalization, and remove filler words.
"""

import json
import os
import subprocess
import threading
import time
import urllib.request
import urllib.error

from utils.resource_path import get_app_data_path
from utils.logger import get_logger

SYSTEM_PROMPT = (
    "You clean up voice-to-text transcriptions. Fix grammar, punctuation, "
    "and capitalization. Remove filler words (um, uh, like, you know). "
    "Output ONLY the corrected text, nothing else.\n\n"
    "Input: um so i went to the store and uh i bought some eggs\n"
    "Output: I went to the store and bought some eggs.\n\n"
    "Input: like do you think that we should you know go to the meeting\n"
    "Output: Do you think that we should go to the meeting?\n\n"
    "Input: the the project is uh almost done i think\n"
    "Output: The project is almost done, I think."
)

# llama-server config
LLAMA_SERVER_PORT = 8787
LLAMA_SERVER_URL = f"http://127.0.0.1:{LLAMA_SERVER_PORT}"
LLAMA_HEALTH_URL = f"{LLAMA_SERVER_URL}/health"
LLAMA_CHAT_URL = f"{LLAMA_SERVER_URL}/v1/chat/completions"

# Model download info
GGUF_REPO = "Qwen/Qwen2.5-0.5B-Instruct-GGUF"
GGUF_FILENAME = "qwen2.5-0.5b-instruct-q4_k_m.gguf"
GGUF_HF_URL = f"https://huggingface.co/{GGUF_REPO}/resolve/main/{GGUF_FILENAME}"

LLAMA_CPP_RELEASE_TAG = "b8175"
LLAMA_CPP_ZIP = f"llama-{LLAMA_CPP_RELEASE_TAG}-bin-win-cpu-x64.zip"
LLAMA_CPP_URL = (
    f"https://github.com/ggml-org/llama.cpp/releases/download/"
    f"{LLAMA_CPP_RELEASE_TAG}/{LLAMA_CPP_ZIP}"
)


class PostProcessor:
    """
    Post-processes transcription output using a small language model
    to fix grammar, punctuation, capitalization, and remove filler words.
    """

    def __init__(self):
        self.logger = get_logger()
        self._lock = threading.Lock()
        self._loaded = False
        self._server_process = None
        self.logger.info("PostProcessor initialized")

    def is_loaded(self):
        """Check if llama-server is running and ready."""
        return self._loaded

    def is_model_downloaded(self):
        """Check if llama-server binary and GGUF model are downloaded."""
        return (
            os.path.isfile(self._get_llama_server_exe())
            and os.path.isfile(self._get_gguf_model_path())
        )

    def load_model(self):
        """Start llama-server subprocess (lazy, thread-safe)."""
        with self._lock:
            if self._loaded:
                return
            try:
                self._start_llama_server()
                self._loaded = True
                self.logger.info("PostProcessor model loaded")
            except Exception as e:
                self.logger.error(f"Failed to load post-processor: {e}", exc_info=True)
                self._loaded = False

    def process(self, raw_text):
        """
        Process transcribed text to fix grammar, punctuation, and filler words.

        Args:
            raw_text: Raw transcription text from Whisper

        Returns:
            Corrected text, or original text if processing fails
        """
        if not raw_text:
            return ""

        if not self._loaded:
            self.load_model()
            if not self._loaded:
                self.logger.warning("PostProcessor not loaded, returning text unchanged")
                return raw_text

        try:
            return self._process_via_api(raw_text)
        except Exception as e:
            self.logger.error(f"Post-processing failed: {e}", exc_info=True)
            return raw_text

    def download_model(self, progress_callback=None):
        """
        Download llama-server binary and GGUF model.

        Args:
            progress_callback: Optional callback(bytes_downloaded, total_bytes)
        """
        import zipfile
        import io

        bin_dir = self._get_bin_dir()
        gguf_dir = self._get_gguf_dir()

        # Download llama-server binary zip
        exe_path = self._get_llama_server_exe()
        if not os.path.isfile(exe_path):
            self.logger.info(f"Downloading llama-server from {LLAMA_CPP_URL}")
            req = urllib.request.Request(LLAMA_CPP_URL)
            with urllib.request.urlopen(req) as resp:
                zip_data = resp.read()

            with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
                for member in zf.namelist():
                    basename = os.path.basename(member)
                    if not basename:
                        continue
                    if basename == "llama-server.exe" or basename.endswith(".dll"):
                        target = os.path.join(bin_dir, basename)
                        with zf.open(member) as src, open(target, "wb") as dst:
                            dst.write(src.read())
                        self.logger.info(f"Extracted: {target}")

        # Download GGUF model
        model_path = self._get_gguf_model_path()
        if not os.path.isfile(model_path):
            self.logger.info(f"Downloading GGUF model from {GGUF_HF_URL}")
            self._download_file(GGUF_HF_URL, model_path, progress_callback)

    def shutdown(self):
        """Shut down llama-server and release resources."""
        with self._lock:
            self._stop_llama_server()
            self._loaded = False
            self.logger.info("PostProcessor shut down")

    # --- Internal helpers ---

    def _get_gguf_dir(self):
        return get_app_data_path("models/postproc-gguf")

    def _get_bin_dir(self):
        return get_app_data_path("bin")

    def _get_llama_server_exe(self):
        return os.path.join(self._get_bin_dir(), "llama-server.exe")

    def _get_gguf_model_path(self):
        return os.path.join(self._get_gguf_dir(), GGUF_FILENAME)

    def _start_llama_server(self):
        exe_path = self._get_llama_server_exe()
        model_path = self._get_gguf_model_path()

        if not os.path.isfile(exe_path):
            raise FileNotFoundError(f"llama-server.exe not found at: {exe_path}")
        if not os.path.isfile(model_path):
            raise FileNotFoundError(f"GGUF model not found at: {model_path}")

        self.logger.info(f"Starting llama-server: {exe_path}")

        cmd = [
            os.path.abspath(exe_path),
            "--model", os.path.abspath(model_path),
            "--port", str(LLAMA_SERVER_PORT),
            "--ctx-size", "512",
            "--threads", "4",
        ]

        self._server_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=(
                subprocess.CREATE_NO_WINDOW
                if hasattr(subprocess, "CREATE_NO_WINDOW")
                else 0
            ),
        )

        self._wait_for_health(timeout=30)
        self.logger.info("llama-server is ready")

    def _wait_for_health(self, timeout=30):
        start = time.time()
        while time.time() - start < timeout:
            try:
                req = urllib.request.Request(LLAMA_HEALTH_URL)
                with urllib.request.urlopen(req, timeout=2) as resp:
                    if resp.status == 200:
                        return
            except (urllib.error.URLError, OSError):
                pass
            time.sleep(0.5)
        raise TimeoutError(f"llama-server did not become healthy within {timeout}s")

    def _stop_llama_server(self):
        if self._server_process is not None:
            self.logger.info("Stopping llama-server process")
            try:
                self._server_process.terminate()
                self._server_process.wait(timeout=5)
            except Exception:
                try:
                    self._server_process.kill()
                except Exception:
                    pass
            self._server_process = None

    def _process_via_api(self, text):
        payload = json.dumps({
            "model": "qwen2.5",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            "temperature": 0.1,
            "max_tokens": 256,
        }).encode("utf-8")

        req = urllib.request.Request(
            LLAMA_CHAT_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        content = result["choices"][0]["message"]["content"]
        return content.strip()

    def _download_file(self, url, dest_path, progress_callback=None):
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            chunk_size = 1024 * 1024

            with open(dest_path, "wb") as f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback:
                        progress_callback(downloaded, total)

        self.logger.info(f"Downloaded: {dest_path}")
```

**Step 2: Verify import works**

Run: `cd src && python -c "from core.post_processor import PostProcessor; pp = PostProcessor(); print('OK')"`
Expected: `PostProcessor initialized` + `OK`

**Step 3: Commit**

```bash
git add src/core/post_processor.py
git commit -m "feat: add PostProcessor class with llama-server backend"
```

---

### Task 3: Wire PostProcessor into TranscriptionWorker

**Files:**
- Modify: `src/main.py:37-62` (TranscriptionWorker class)

**Step 1: Add post_processor parameter to TranscriptionWorker**

Change `TranscriptionWorker.__init__` signature from:
```python
def __init__(self, transcriber, audio_data, logger=None):
```
to:
```python
def __init__(self, transcriber, audio_data, post_processor=None, logger=None):
```

Add `self.post_processor = post_processor` in `__init__`.

**Step 2: Add post-processing step to `run()`**

After the `text = self.transcriber.transcribe(self.audio_data)` line and its log, add:

```python
if text and self.post_processor:
    if self.logger:
        self.logger.info("Running post-processing...")
    text = self.post_processor.process(text)
    if self.logger:
        self.logger.info(f"Post-processing finished, got {len(text)} characters")
```

**Step 3: Commit**

```bash
git add src/main.py
git commit -m "feat: add post-processing step to TranscriptionWorker"
```

---

### Task 4: Wire PostProcessor lifecycle into VTTApplication

**Files:**
- Modify: `src/main.py:65-428` (VTTApplication class)

**Step 1: Import PostProcessor**

Add to the imports at the top of `main.py`:
```python
from core.post_processor import PostProcessor
```

**Step 2: Initialize PostProcessor in `__init__`**

After the `self.dictionary = DictionaryProcessor(...)` line (~line 92), add:

```python
self.post_processor = None
if self.config.get_post_processing_enabled():
    self.post_processor = PostProcessor()
```

**Step 3: Pass post_processor to TranscriptionWorker in `start_transcription()`**

In `start_transcription()`, change the worker creation (~line 229) from:
```python
self.transcription_worker = TranscriptionWorker(
    self.transcriber, audio_data, self.logger
)
```
to:
```python
self.transcription_worker = TranscriptionWorker(
    self.transcriber, audio_data, self.post_processor, self.logger
)
```

**Step 4: Toggle PostProcessor in `on_settings_changed()`**

After the typing speed update block (~line 413), add:

```python
# Update post-processing
pp_enabled = self.config.get_post_processing_enabled()
if pp_enabled and self.post_processor is None:
    self.post_processor = PostProcessor()
elif not pp_enabled and self.post_processor is not None:
    self.post_processor.shutdown()
    self.post_processor = None
```

**Step 5: Shut down PostProcessor in `quit()`**

In the `quit()` method, before `QApplication.quit()`, add:

```python
if self.post_processor:
    self.post_processor.shutdown()
```

**Step 6: Commit**

```bash
git add src/main.py
git commit -m "feat: wire PostProcessor lifecycle into VTTApplication"
```

---

### Task 5: Add post-processing checkbox to Settings UI

**Files:**
- Modify: `src/gui/settings_dialog.py:434-462` (create_model_group)
- Modify: `src/gui/settings_dialog.py:673-701` (load_current_settings)
- Modify: `src/gui/settings_dialog.py:702-778` (save_settings)

**Step 1: Add checkbox to `create_model_group()`**

After the `info_label` block (after `layout.addRow("", info_label)` on line 459), add:

```python
# Post-processing checkbox
from PySide6.QtWidgets import QCheckBox
self.post_processing_cb = QCheckBox("Post-processing")
pp_desc = QLabel("Clean up grammar, punctuation, and filler words")
pp_desc.setStyleSheet("color: rgba(255, 255, 255, 140); font-size: 11px;")

pp_row = QHBoxLayout()
pp_row.addWidget(self.post_processing_cb)
pp_row.addWidget(pp_desc)
pp_row.addStretch()
layout.addRow("", pp_row)
```

Also add `QCheckBox` to the import list at the top of the file:
```python
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QGroupBox, QLineEdit,
    QMessageBox, QFormLayout, QProgressBar, QRadioButton,
    QButtonGroup, QGridLayout, QFrame, QCheckBox
)
```

**Step 2: Load post-processing state in `load_current_settings()`**

At the end of `load_current_settings()` (after the typing method block), add:

```python
# Post-processing
self.post_processing_cb.setChecked(self.config.get_post_processing_enabled())
```

**Step 3: Save post-processing state in `save_settings()`**

In `save_settings()`, after `use_clipboard = self.typing_paste_radio.isChecked()` (~line 709), add:

```python
pp_enabled = self.post_processing_cb.isChecked()
```

In the change detection block, after the `use_clipboard` check, add:

```python
old_pp = self.config.get_post_processing_enabled()
if pp_enabled != old_pp:
    changes.append(f"Post-processing → {'On' if pp_enabled else 'Off'}")
```

In the "Save to config" block, before `self.config.save()`, add:

```python
self.config.set_post_processing_enabled(pp_enabled)
```

**Step 4: Add model download trigger**

In `save_settings()`, after the Whisper model download block (`if not dlg.succeeded: return`), add a new block for post-processing model download:

```python
# Download post-processing model if enabling for the first time
if pp_enabled and not old_pp:
    from core.post_processor import PostProcessor
    pp = PostProcessor()
    if not pp.is_model_downloaded():
        dlg = PostProcessingDownloadDialog(self)
        dlg.exec()
        if not dlg.succeeded:
            return
```

**Step 5: Create `PostProcessingDownloadDialog`**

Add this class in `settings_dialog.py` after `ModelDownloadDialog` (after line 321):

```python
class _PPDownloadWorker(QObject):
    """Background worker for downloading post-processing model."""

    finished = Signal()
    error = Signal(str)
    progress = Signal(int, int)  # downloaded, total

    def __init__(self):
        super().__init__()

    def run(self):
        try:
            from core.post_processor import PostProcessor
            pp = PostProcessor()
            pp.download_model(progress_callback=self._on_progress)
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))

    def _on_progress(self, downloaded, total):
        self.progress.emit(downloaded, total)


class PostProcessingDownloadDialog(RoundedDialog):
    """Progress dialog shown while downloading post-processing model."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Downloading Post-Processing Model")
        self.setMinimumWidth(420)
        self._success = False

        layout = QVBoxLayout()
        layout.setSpacing(12)

        self._status = QLabel("Downloading llama-server and Qwen 2.5 model...")
        self._status.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._status)

        self._bar = QProgressBar()
        self._bar.setMinimum(0)
        self._bar.setMaximum(100)
        self._bar.setValue(0)
        self._bar.setTextVisible(True)
        self._bar.setFormat("%v%")
        self._bar.setMinimumHeight(28)
        layout.addWidget(self._bar)

        self._time_label = QLabel("Elapsed: 0:00")
        self._time_label.setStyleSheet("color: rgba(255, 255, 255, 140); font-size: 11px;")
        layout.addWidget(self._time_label)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

        self._start_time = time.time()

        # Elapsed timer
        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start(500)

        # Background download thread
        self._thread = QThread()
        self._worker = _PPDownloadWorker()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.progress.connect(self._on_progress)

        self._thread.start()

    def _tick(self):
        elapsed = time.time() - self._start_time
        m, s = divmod(int(elapsed), 60)
        self._time_label.setText(f"Elapsed: {m}:{s:02d}")

    def _on_progress(self, downloaded, total):
        if total > 0:
            pct = min(99, int(downloaded / total * 100))
            self._bar.setValue(pct)
            mb_done = downloaded / (1024 * 1024)
            mb_total = total / (1024 * 1024)
            self._status.setText(f"Downloading model... {mb_done:.0f} / {mb_total:.0f} MB")

    def _on_finished(self):
        self._tick_timer.stop()
        self._bar.setValue(100)
        self._success = True
        self._cleanup()
        self.accept()

    def _on_error(self, msg):
        self._tick_timer.stop()
        self._cleanup()
        MessageBox.critical(self, "Download Failed", f"Failed to download model:\n\n{msg}")
        self.reject()

    def _cleanup(self):
        if self._thread:
            self._thread.quit()
            self._thread.wait(2000)
            self._thread.deleteLater()
            self._thread = None
        if self._worker:
            self._worker.deleteLater()
            self._worker = None

    def closeEvent(self, event):
        self._cleanup()
        event.accept()

    @property
    def succeeded(self):
        return self._success
```

**Step 6: Commit**

```bash
git add src/gui/settings_dialog.py
git commit -m "feat: add post-processing checkbox and model download dialog"
```

---

### Task 6: Update CLAUDE.md and final commit

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Update abandoned work section**

In `CLAUDE.md`, change the abandoned work entry for LLM post-processing from:
```
- **LLM post-processing** — tried llama-server (llama.cpp) with Qwen2.5 0.5B/1.5B/3B/7B for grammar cleanup and formatting commands. Grammar worked but formatting commands (bullets, numbered lists, scratch that) failed — generic models can't reliably interpret voice commands as formatting. Would need fine-tuned models or cloud APIs. Removed.
```
to:
```
- **LLM formatting commands** — tried Qwen2.5 0.5B–7B for voice formatting commands (bullets, numbered lists, scratch that). Generic models can't reliably interpret these. Grammar/punctuation cleanup was re-added without formatting commands.
```

Add to the Architecture section, under `core/`:
```
    post_processor.py       - LLM post-processing via llama-server (grammar/punctuation/filler cleanup)
```

Add to the Transcription Flow, step 4:
```
4. VTTApplication.on_transcription_complete() applies post-processing (if enabled) then dictionary replacements via DictionaryProcessor
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with post-processor architecture"
```

---

### Task 7: Push to GitHub

**Step 1: Push all commits**

```bash
git push origin main
```
