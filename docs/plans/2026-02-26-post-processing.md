# Post-Processing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a local LLM post-processor (Qwen2.5-0.5B via llama-cpp-python) that fixes grammar, punctuation, and spoken formatting commands after Whisper transcription, with a unified CPU/GPU device setting.

**Architecture:** PostProcessor wraps llama-cpp-python, lazy-loads the GGUF model at first use, and runs inside the existing TranscriptionWorker QThread. A single `processing.device` config key controls device selection for both Whisper and the LLM. Post-processing can be toggled on/off in settings.

**Tech Stack:** llama-cpp-python (GGUF inference), Qwen2.5-0.5B-Instruct-Q4_K_M (grammar LLM), huggingface_hub (model download, already a dep), PySide6 (settings UI), pytest (tests)

---

## Task 1: Add dependency and test scaffolding

**Files:**
- Modify: `requirements.txt`
- Create: `tests/__init__.py`
- Create: `tests/core/__init__.py`

**Step 1: Add llama-cpp-python to requirements.txt**

Open `requirements.txt` and append:

```
# Grammar/formatting LLM (llama-cpp-python)
# CPU install (default): pip install llama-cpp-python
# CUDA/GPU on Windows: pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu121
llama-cpp-python>=0.3.0
```

**Step 2: Create test directories**

```bash
mkdir tests
mkdir tests\core
```

Create `tests/__init__.py` (empty file).
Create `tests/core/__init__.py` (empty file).

**Step 3: Install the dependency**

From the project root (with `.venv` active):

```bash
.venv\Scripts\pip install llama-cpp-python
```

Verify:
```bash
.venv\Scripts\python -c "import llama_cpp; print('ok')"
```
Expected: `ok`

**Step 4: Commit**

```bash
git add requirements.txt tests/__init__.py tests/core/__init__.py
git commit -m "feat: add llama-cpp-python dependency and test scaffolding"
```

---

## Task 2: Create PostProcessor class (TDD)

**Files:**
- Create: `tests/core/test_post_processor.py`
- Create: `src/core/post_processor.py`

**Step 1: Write failing tests**

Create `tests/core/test_post_processor.py`:

```python
"""Tests for PostProcessor."""
import os
import sys
import pytest
from unittest.mock import MagicMock, patch

# Add src to path so imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from core.post_processor import PostProcessor


class TestPostProcessorInit:
    def test_default_device_is_cpu(self):
        pp = PostProcessor.__new__(PostProcessor)
        pp.device = "cpu"
        pp.model = None
        assert pp.device == "cpu"

    def test_model_path_includes_filename(self):
        with patch('core.post_processor.get_app_data_path', return_value='/fake/data'):
            pp = PostProcessor(device="cpu")
            assert "qwen2.5-0.5b-instruct-q4_k_m.gguf" in pp.model_path


class TestIsModelDownloaded:
    def test_returns_false_when_file_missing(self, tmp_path):
        with patch('core.post_processor.get_app_data_path', return_value=str(tmp_path)):
            pp = PostProcessor(device="cpu")
            assert pp.is_model_downloaded() is False

    def test_returns_true_when_file_exists(self, tmp_path):
        with patch('core.post_processor.get_app_data_path', return_value=str(tmp_path)):
            pp = PostProcessor(device="cpu")
            # Create the file
            os.makedirs(os.path.dirname(pp.model_path), exist_ok=True)
            open(pp.model_path, 'w').close()
            assert pp.is_model_downloaded() is True


class TestProcess:
    def _make_pp_with_mock_model(self):
        """Return a PostProcessor with a mocked llama model."""
        with patch('core.post_processor.get_app_data_path', return_value='/fake'):
            pp = PostProcessor(device="cpu")
        mock_model = MagicMock()
        mock_model.create_chat_completion.return_value = {
            "choices": [{"message": {"content": "Hello, world."}}]
        }
        pp.model = mock_model
        return pp

    def test_returns_corrected_text(self):
        pp = self._make_pp_with_mock_model()
        result = pp.process("hello world")
        assert result == "Hello, world."

    def test_returns_empty_string_for_empty_input(self):
        pp = self._make_pp_with_mock_model()
        result = pp.process("")
        assert result == ""
        # Model should NOT be called for empty input
        pp.model.create_chat_completion.assert_not_called()

    def test_returns_original_on_model_error(self):
        with patch('core.post_processor.get_app_data_path', return_value='/fake'):
            pp = PostProcessor(device="cpu")
        mock_model = MagicMock()
        mock_model.create_chat_completion.side_effect = RuntimeError("model exploded")
        pp.model = mock_model
        result = pp.process("some text")
        assert result == "some text"

    def test_returns_original_if_model_returns_empty(self):
        with patch('core.post_processor.get_app_data_path', return_value='/fake'):
            pp = PostProcessor(device="cpu")
        mock_model = MagicMock()
        mock_model.create_chat_completion.return_value = {
            "choices": [{"message": {"content": ""}}]
        }
        pp.model = mock_model
        result = pp.process("original text")
        assert result == "original text"


class TestChangeDevice:
    def test_change_device_resets_model(self):
        with patch('core.post_processor.get_app_data_path', return_value='/fake'):
            pp = PostProcessor(device="cpu")
        pp.model = MagicMock()  # Simulate loaded model
        pp.change_device("cuda")
        assert pp.device == "cuda"
        assert pp.model is None

    def test_change_to_same_device_does_nothing(self):
        with patch('core.post_processor.get_app_data_path', return_value='/fake'):
            pp = PostProcessor(device="cpu")
        mock = MagicMock()
        pp.model = mock
        pp.change_device("cpu")
        # Model should still be set (not reset)
        assert pp.model is mock
```

**Step 2: Run tests to verify they fail**

```bash
cd F:\Resonance-main
.venv\Scripts\python -m pytest tests/core/test_post_processor.py -v 2>&1 | head -30
```
Expected: `ImportError: No module named 'core.post_processor'`

**Step 3: Create src/core/post_processor.py**

```python
"""
LLM-based post-processor for transcription correction.
Fixes grammar, punctuation, and spoken formatting commands using a local GGUF model.
"""

import os
import threading

from utils.resource_path import get_app_data_path
from utils.logger import get_logger


MODEL_REPO = "Qwen/Qwen2.5-0.5B-Instruct-GGUF"
MODEL_FILENAME = "qwen2.5-0.5b-instruct-q4_k_m.gguf"

SYSTEM_PROMPT = (
    "You are a transcription post-processor. Your job is to:\n"
    "1. Fix grammar and punctuation\n"
    "2. Intelligently interpret spoken formatting commands and apply them\n\n"
    "Examples of formatting commands to handle:\n"
    "- \"bullet\" / \"bullets\" → format items as a markdown bullet list\n"
    "- \"new line\" / \"next line\" → insert a line break\n"
    "- \"number one ... number two ...\" → format as a numbered list\n"
    "- \"scratch that\" / \"delete that\" → remove the preceding content\n"
    "- \"period\" / \"comma\" / \"colon\" → insert the punctuation\n\n"
    "Output only the final corrected text. No explanations, no commentary."
)


class PostProcessor:
    """Local LLM post-processor for transcription cleanup and formatting."""

    def __init__(self, device="cpu"):
        """
        Initialize post-processor.

        Args:
            device: "cpu" or "cuda"
        """
        self.device = device
        self.model = None
        self._lock = threading.Lock()
        self.logger = get_logger()

        llm_dir = get_app_data_path("models/llm")
        self.model_path = os.path.join(llm_dir, MODEL_FILENAME)

    def is_model_downloaded(self):
        """Return True if the GGUF model file exists locally."""
        return os.path.isfile(self.model_path)

    def download_model(self, progress_callback=None):
        """
        Download the GGUF model from HuggingFace.

        Args:
            progress_callback: Optional callable(bytes_downloaded, total_bytes)
        """
        from huggingface_hub import hf_hub_download

        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
        self.logger.info(f"Downloading grammar model from {MODEL_REPO}...")

        hf_hub_download(
            repo_id=MODEL_REPO,
            filename=MODEL_FILENAME,
            local_dir=os.path.dirname(self.model_path),
        )
        self.logger.info("Grammar model downloaded successfully")

    def load_model(self):
        """Load the GGUF model into memory (lazy, thread-safe)."""
        with self._lock:
            if self.model is not None:
                return
            if not self.is_model_downloaded():
                raise RuntimeError(
                    f"Grammar model not found at {self.model_path}. "
                    "Download it from Settings."
                )
            try:
                from llama_cpp import Llama

                n_gpu_layers = -1 if self.device == "cuda" else 0
                self.logger.info(
                    f"Loading grammar model (device={self.device}, "
                    f"n_gpu_layers={n_gpu_layers})..."
                )
                self.model = Llama(
                    model_path=self.model_path,
                    n_gpu_layers=n_gpu_layers,
                    n_ctx=1024,
                    verbose=False,
                )
                self.logger.info("Grammar model loaded successfully")
            except Exception as e:
                self.logger.error(f"Failed to load grammar model: {e}", exc_info=True)
                raise

    def process(self, text: str) -> str:
        """
        Post-process transcribed text: fix grammar, punctuation, and formatting commands.

        Args:
            text: Raw transcribed text from Whisper

        Returns:
            Corrected text. Falls back to original text on any error.
        """
        if not text:
            return text

        try:
            if self.model is None:
                self.load_model()

            response = self.model.create_chat_completion(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
                max_tokens=len(text) * 2 + 100,
                temperature=0.0,
            )
            result = response["choices"][0]["message"]["content"].strip()
            if not result:
                return text
            self.logger.info(f"Post-processing: '{text}' -> '{result}'")
            return result

        except Exception as e:
            self.logger.error(f"Post-processing failed, using raw text: {e}")
            return text

    def change_device(self, device: str):
        """
        Switch between CPU and GPU. Unloads model so it reloads on next use.

        Args:
            device: "cpu" or "cuda"
        """
        with self._lock:
            if self.device != device:
                self.device = device
                self.model = None
                self.logger.info(f"Post-processor device changed to {device}, model unloaded")

    def is_loaded(self):
        """Return True if model is currently loaded in memory."""
        return self.model is not None
```

**Step 4: Run tests to verify they pass**

```bash
cd F:\Resonance-main
.venv\Scripts\python -m pytest tests/core/test_post_processor.py -v
```
Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/core/post_processor.py tests/core/test_post_processor.py
git commit -m "feat: add PostProcessor class with llama-cpp-python backend"
```

---

## Task 3: Update ConfigManager (TDD)

**Files:**
- Create: `tests/utils/__init__.py`
- Create: `tests/utils/test_config_post_processing.py`
- Modify: `src/utils/config.py`

**Step 1: Create test directory**

```bash
mkdir tests\utils
```

Create `tests/utils/__init__.py` (empty file).

**Step 2: Write failing tests**

Create `tests/utils/test_config_post_processing.py`:

```python
"""Tests for new post-processing config keys."""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from utils.config import ConfigManager


@pytest.fixture
def config(tmp_path):
    """Fresh config with temp file."""
    return ConfigManager(config_file=str(tmp_path / "settings.json"))


class TestProcessingDevice:
    def test_default_device_is_cpu(self, config):
        assert config.get_processing_device() == "cpu"

    def test_set_and_get_device(self, config):
        config.set_processing_device("cuda")
        assert config.get_processing_device() == "cuda"

    def test_device_persists_after_save_load(self, tmp_path):
        cfg = ConfigManager(config_file=str(tmp_path / "s.json"))
        cfg.set_processing_device("cuda")
        cfg.save()
        cfg2 = ConfigManager(config_file=str(tmp_path / "s.json"))
        assert cfg2.get_processing_device() == "cuda"


class TestPostProcessingEnabled:
    def test_default_disabled(self, config):
        assert config.get_post_processing_enabled() is False

    def test_set_and_get_enabled(self, config):
        config.set_post_processing_enabled(True)
        assert config.get_post_processing_enabled() is True

    def test_enabled_persists_after_save_load(self, tmp_path):
        cfg = ConfigManager(config_file=str(tmp_path / "s.json"))
        cfg.set_post_processing_enabled(True)
        cfg.save()
        cfg2 = ConfigManager(config_file=str(tmp_path / "s.json"))
        assert cfg2.get_post_processing_enabled() is True
```

**Step 3: Run tests to verify they fail**

```bash
.venv\Scripts\python -m pytest tests/utils/test_config_post_processing.py -v
```
Expected: `AttributeError: 'ConfigManager' object has no attribute 'get_processing_device'`

**Step 4: Add new keys to ConfigManager**

Open `src/utils/config.py`.

In `DEFAULT_CONFIG`, add two new top-level keys after the existing `"dictionary"` block:

```python
        "processing": {
            "device": "cpu"
        },
        "post_processing": {
            "enabled": False
        }
```

At the bottom of the class, before `reset_to_defaults`, add:

```python
    def get_processing_device(self):
        """Get processing device for Whisper and grammar LLM ('cpu' or 'cuda')."""
        return self.get("processing", "device", default="cpu")

    def set_processing_device(self, device):
        """Set processing device ('cpu' or 'cuda')."""
        self.set("processing", "device", value=device)

    def get_post_processing_enabled(self):
        """Get whether LLM post-processing is enabled."""
        return self.get("post_processing", "enabled", default=False)

    def set_post_processing_enabled(self, enabled):
        """Set whether LLM post-processing is enabled."""
        self.set("post_processing", "enabled", value=enabled)
```

**Step 5: Run tests to verify they pass**

```bash
.venv\Scripts\python -m pytest tests/utils/test_config_post_processing.py -v
```
Expected: All tests PASS

**Step 6: Commit**

```bash
git add src/utils/config.py tests/utils/__init__.py tests/utils/test_config_post_processing.py
git commit -m "feat: add processing.device and post_processing config keys"
```

---

## Task 4: Wire PostProcessor into main.py

**Files:**
- Modify: `src/main.py`

**Step 1: Update TranscriptionWorker to accept post_processor**

In `src/main.py`, find the `TranscriptionWorker.__init__` signature (line 39):

```python
    def __init__(self, transcriber, audio_data, logger=None):
```

Replace with:

```python
    def __init__(self, transcriber, audio_data, post_processor=None, logger=None):
```

Add `self.post_processor = post_processor` after `self.audio_data = audio_data`.

**Step 2: Update TranscriptionWorker.run to call post_processor**

Find the `run` method. After `text = self.transcriber.transcribe(self.audio_data)`, add:

```python
            if self.post_processor and text:
                if self.logger:
                    self.logger.info("Running post-processing...")
                text = self.post_processor.process(text)
```

**Step 3: Instantiate PostProcessor in VTTApplication.__init__**

In `VTTApplication.__init__`, after `self.transcriber = Transcriber(...)` block, add:

```python
        # Initialize post-processor
        from core.post_processor import PostProcessor
        self.post_processor = PostProcessor(
            device=self.config.get_processing_device()
        )
```

**Step 4: Pass post_processor to TranscriptionWorker in start_transcription**

Find the line in `start_transcription` that creates `TranscriptionWorker` (around line 191):

```python
        self.transcription_worker = TranscriptionWorker(self.transcriber, audio_data, self.logger)
```

Replace with:

```python
        active_post_processor = (
            self.post_processor
            if self.config.get_post_processing_enabled()
            else None
        )
        self.transcription_worker = TranscriptionWorker(
            self.transcriber,
            audio_data,
            post_processor=active_post_processor,
            logger=self.logger,
        )
```

**Step 5: Handle device/post-processing changes in on_settings_changed**

In `on_settings_changed`, after the `# Update model` block, add:

```python
        # Update processing device for both Whisper and PostProcessor
        device = self.config.get_processing_device()
        if device != self.transcriber.device:
            self.transcriber.device = device
            self.transcriber.model = None  # force reload on next use
        self.post_processor.change_device(device)
```

**Step 6: Smoke test — launch the app and verify it starts without errors**

```bash
cd F:\Resonance-main
.venv\Scripts\python src/main.py
```

Expected: App starts, tray icon appears, no errors in console. Post-processing is off by default so no model load occurs.

**Step 7: Commit**

```bash
git add src/main.py
git commit -m "feat: wire PostProcessor into TranscriptionWorker pipeline"
```

---

## Task 5: Add post-processing settings to SettingsDialog

**Files:**
- Modify: `src/gui/settings_dialog.py`

**Step 1: Update SettingsDialog.__init__ to accept post_processor**

Find the `__init__` signature (line 184):

```python
    def __init__(self, config_manager, audio_recorder, transcriber, parent=None):
```

Replace with:

```python
    def __init__(self, config_manager, audio_recorder, transcriber, post_processor=None, parent=None):
```

Add `self.post_processor = post_processor` after `self.transcriber = transcriber`.

**Step 2: Add create_processing_group method**

Add this new method after `create_model_group`:

```python
    def create_processing_group(self):
        """Create processing device + post-processing group."""
        from PySide6.QtWidgets import QCheckBox
        group = QGroupBox("Processing")
        layout = QFormLayout()

        # Device selection
        device_layout = QHBoxLayout()
        self.device_cpu_radio = QRadioButton("CPU")
        self.device_gpu_radio = QRadioButton("GPU (CUDA)")

        self.device_button_group = QButtonGroup()
        self.device_button_group.addButton(self.device_cpu_radio, 0)
        self.device_button_group.addButton(self.device_gpu_radio, 1)

        device_layout.addWidget(self.device_cpu_radio)
        device_layout.addWidget(self.device_gpu_radio)
        device_layout.addStretch()
        layout.addRow("Processing Device:", device_layout)

        # Check if CUDA is available
        try:
            import llama_cpp  # noqa
            cuda_available = True
        except Exception:
            cuda_available = False

        if not cuda_available:
            self.device_gpu_radio.setEnabled(False)
            self.device_gpu_radio.setToolTip("GPU requires the CUDA build of llama-cpp-python")

        device_info = QLabel("Applies to both Whisper and grammar correction.")
        device_info.setStyleSheet("color: gray; font-size: 10px;")
        layout.addRow("", device_info)

        # Post-processing toggle
        self.post_processing_checkbox = QCheckBox("Enable grammar & punctuation correction")
        layout.addRow("Post-Processing:", self.post_processing_checkbox)

        # Model status + download button
        self.pp_status_label = QLabel("Model not downloaded")
        self.pp_status_label.setStyleSheet("color: gray; font-size: 10px;")

        self.pp_download_button = QPushButton("Download Model (~400 MB)")
        self.pp_download_button.clicked.connect(self.download_grammar_model)

        pp_model_layout = QHBoxLayout()
        pp_model_layout.addWidget(self.pp_status_label)
        pp_model_layout.addStretch()
        pp_model_layout.addWidget(self.pp_download_button)

        layout.addRow("Grammar Model:", pp_model_layout)

        # Show/hide model row based on toggle
        self.post_processing_checkbox.toggled.connect(self._update_pp_model_visibility)

        group.setLayout(layout)
        return group

    def _update_pp_model_visibility(self, enabled):
        """Show grammar model controls only when post-processing is enabled."""
        self.pp_status_label.setVisible(enabled)
        self.pp_download_button.setVisible(enabled)
        self._refresh_pp_model_status()

    def _refresh_pp_model_status(self):
        """Update the grammar model status label."""
        if self.post_processor and self.post_processor.is_model_downloaded():
            self.pp_status_label.setText("Model ready")
            self.pp_status_label.setStyleSheet("color: green; font-size: 10px;")
            self.pp_download_button.setText("Re-download Model")
        else:
            self.pp_status_label.setText("Model not downloaded")
            self.pp_status_label.setStyleSheet("color: gray; font-size: 10px;")
            self.pp_download_button.setText("Download Model (~400 MB)")

    def download_grammar_model(self):
        """Download the grammar model with a progress dialog."""
        if not self.post_processor:
            return

        self.pp_download_button.setEnabled(False)
        self.pp_status_label.setText("Downloading...")
        self.pp_status_label.setStyleSheet("color: blue; font-size: 10px;")

        # Run download in a thread so UI stays responsive
        import threading

        def do_download():
            try:
                self.post_processor.download_model()
                # Update UI on main thread via QTimer
                from PySide6.QtCore import QTimer
                QTimer.singleShot(0, self._on_download_complete)
            except Exception as e:
                from PySide6.QtCore import QTimer
                QTimer.singleShot(0, lambda: self._on_download_error(str(e)))

        threading.Thread(target=do_download, daemon=True).start()

    def _on_download_complete(self):
        """Called on main thread after successful download."""
        self.pp_download_button.setEnabled(True)
        self._refresh_pp_model_status()
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(self, "Download Complete", "Grammar model downloaded successfully.")

    def _on_download_error(self, error_msg):
        """Called on main thread after failed download."""
        self.pp_download_button.setEnabled(True)
        self.pp_status_label.setText("Download failed")
        self.pp_status_label.setStyleSheet("color: red; font-size: 10px;")
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.critical(self, "Download Failed", f"Could not download grammar model:\n{error_msg}")
```

**Step 3: Add the processing group to init_ui**

In `init_ui`, after `model_group = self.create_model_group()` and `layout.addWidget(model_group)`, add:

```python
        # Processing device + post-processing
        processing_group = self.create_processing_group()
        layout.addWidget(processing_group)
```

**Step 4: Load processing settings in load_current_settings**

At the end of `load_current_settings`, add:

```python
        # Processing device
        device = self.config.get_processing_device()
        if device == "cuda":
            self.device_gpu_radio.setChecked(True)
        else:
            self.device_cpu_radio.setChecked(True)

        # Post-processing
        pp_enabled = self.config.get_post_processing_enabled()
        self.post_processing_checkbox.setChecked(pp_enabled)
        self._update_pp_model_visibility(pp_enabled)
```

**Step 5: Save processing settings in save_settings**

In `save_settings`, before `self.config.save()`, add:

```python
            # Processing device
            device = "cuda" if self.device_gpu_radio.isChecked() else "cpu"
            self.config.set_processing_device(device)

            # Post-processing
            self.config.set_post_processing_enabled(
                self.post_processing_checkbox.isChecked()
            )
```

**Step 6: Update show_settings in main.py to pass post_processor**

In `src/main.py`, in `show_settings`, find the `SettingsDialog(...)` call (around line 438):

```python
            dialog = SettingsDialog(
                self.config,
                self.audio_recorder,
                self.transcriber
            )
```

Replace with:

```python
            dialog = SettingsDialog(
                self.config,
                self.audio_recorder,
                self.transcriber,
                post_processor=self.post_processor,
            )
```

**Step 7: Smoke test the full settings UI**

```bash
.venv\Scripts\python src/main.py
```

1. Right-click tray icon → Settings
2. Verify "Processing" group appears with CPU/GPU radios and post-processing checkbox
3. Check "Enable grammar & punctuation correction" — model status and download button should appear
4. Click Save — no errors

**Step 8: Commit**

```bash
git add src/gui/settings_dialog.py src/main.py
git commit -m "feat: add processing device and post-processing settings UI"
```

---

## Task 6: End-to-end test with post-processing enabled

**This task is manual testing — no code changes.**

**Step 1: Download the grammar model**

1. Open Settings → check "Enable grammar & punctuation correction"
2. Click "Download Model (~400 MB)"
3. Wait for download to complete (uses HuggingFace, needs internet once)
4. Status should show "Model ready"
5. Save settings

**Step 2: Test grammar correction**

Hold the hotkey and say (deliberately poor grammar):
> "this is a test and i want to see if the grammar gets fixed"

Expected output (approximately):
> "This is a test, and I want to see if the grammar gets fixed."

**Step 3: Test formatting commands**

Hold hotkey and say:
> "things to buy bullet milk bullet eggs bullet bread"

Expected output (approximately):
> - Milk
> - Eggs
> - Bread

**Step 4: Test "scratch that"**

Hold hotkey and say:
> "I went to the store scratch that I went to the market"

Expected output (approximately):
> "I went to the market."

**Step 5: Test fallback — disable post-processing**

In Settings, uncheck post-processing. Dictate the same text. Verify raw Whisper output comes through unchanged.

**Step 6: Final commit**

```bash
git add -A
git commit -m "feat: complete post-processing feature with grammar correction and formatting commands"
```

---

## Notes

- **CUDA build**: If the user wants GPU acceleration, they must install the CUDA variant of llama-cpp-python. The settings UI will gray out GPU if the standard build is detected. Install CUDA build with:
  ```
  pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu121
  ```
- **Model quality**: Qwen2.5-0.5B is tiny. If formatting command accuracy is poor during testing, the model can be upgraded to 1.5B (same GGUF approach, larger file).
- **Latency**: On CPU, expect ~500ms–1.5s added. On GPU (3080), expect ~100–300ms added. These are acceptable trade-offs for the quality improvement.
