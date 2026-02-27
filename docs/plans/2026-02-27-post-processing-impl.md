# Post-Processing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add local LLM post-processing after Whisper transcription to fix punctuation, capitalization, grammar, and interpret spoken formatting commands.

**Architecture:** A `PostProcessor` class with swappable backends (onnxruntime-genai and llama-server) sits between transcription and dictionary replacement. Benchmarking determines the default backend.

**Tech Stack:** onnxruntime-genai, llama.cpp (llama-server binary), Qwen2.5-0.5B-Instruct (INT4/Q4_K_M)

---

### Task 1: Install onnxruntime-genai and verify it works

**Files:**
- Modify: `pyproject.toml` (add optional dependency)
- Create: `scripts/benchmark_postproc.py`

**Step 1: Add onnxruntime-genai as optional dependency**

In `pyproject.toml`, add a new optional dependency group under `[project.optional-dependencies]`:

```toml
[project.optional-dependencies]
dev = [
    "pyinstaller>=5.13.0",
    "pillow>=10.0.0",
]
postproc = [
    "onnxruntime-genai>=0.12.0",
]
```

**Step 2: Install it**

Run: `uv pip install onnxruntime-genai --python .venv/Scripts/python.exe`

Expected: Successful install with pre-built wheel.

**Step 3: Write a quick smoke test script**

Create `scripts/benchmark_postproc.py`:

```python
"""Benchmark post-processing backends for Resonance."""

import time
import sys
import os

# Add src to path so we can import app modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

SYSTEM_PROMPT = (
    "You are a transcription post-processor. Fix grammar, punctuation, and "
    "capitalization. Interpret spoken formatting commands:\n"
    "- 'new line' / 'next line' -> insert a line break\n"
    "- 'bullet' / 'bullets' -> markdown bullet list\n"
    "- 'number one ... number two ...' -> numbered list\n"
    "- 'scratch that' / 'delete that' -> remove preceding content\n"
    "- 'period' / 'comma' / 'colon' -> insert punctuation\n"
    "Output only the corrected text. No explanations."
)

TEST_INPUTS = [
    "hello how are you doing today",
    "i went to the store and bought some milk and bread and eggs",
    "the quick brown fox jumps over the lazy dog period",
    "bullet buy groceries bullet clean the house bullet walk the dog",
    "dear john new line i hope this message finds you well new line sincerely mary",
    "number one first item number two second item number three third item",
    "i think we should scratch that actually lets go with the other option instead",
]


def benchmark_onnx():
    """Benchmark onnxruntime-genai backend."""
    try:
        import onnxruntime_genai as og
    except ImportError:
        print("onnxruntime-genai not installed. Run: uv pip install onnxruntime-genai")
        return

    # Check for model
    from utils.resource_path import get_app_data_path
    model_dir = get_app_data_path("models/postproc-onnx")

    if not os.path.isdir(model_dir) or not any(
        f.endswith('.onnx') or f.endswith('.onnx_data') for f in os.listdir(model_dir)
        if os.path.isfile(os.path.join(model_dir, f))
    ):
        print(f"ONNX model not found at {model_dir}")
        print("Download a Qwen2.5-0.5B-Instruct ONNX INT4 model and place it there.")
        print("E.g.: huggingface-cli download hazemmabbas/Qwen2.5-0.5B-int4-block-32-acc-3-Instruct-onnx-cpu --local-dir", model_dir)
        return

    print("Loading ONNX model...")
    t0 = time.perf_counter()
    model = og.Model(model_dir)
    tokenizer = og.Tokenizer(model)
    load_time = time.perf_counter() - t0
    print(f"Model loaded in {load_time:.2f}s")

    print("\n--- ONNX Runtime GenAI Benchmark ---\n")

    for i, text in enumerate(TEST_INPUTS):
        prompt = f"<|im_start|>system\n{SYSTEM_PROMPT}<|im_end|>\n<|im_start|>user\n{text}<|im_end|>\n<|im_start|>assistant\n"

        params = og.GeneratorParams(model)
        params.set_search_options(max_length=256, temperature=0.1)

        input_tokens = tokenizer.encode(prompt)
        params.input_ids = input_tokens

        t0 = time.perf_counter()
        generator = og.Generator(model, params)

        output_tokens = []
        while not generator.is_done():
            generator.compute_logits()
            generator.generate_next_token()
            token = generator.get_next_tokens()[0]
            output_tokens.append(token)

        result = tokenizer.decode(output_tokens)
        elapsed = time.perf_counter() - t0
        tps = len(output_tokens) / elapsed if elapsed > 0 else 0

        print(f"[{i+1}] {elapsed:.2f}s ({len(output_tokens)} tokens, {tps:.1f} tok/s)")
        print(f"    IN:  {text}")
        print(f"    OUT: {result}")
        print()

    del generator, model


def benchmark_llama_server():
    """Benchmark llama-server subprocess backend."""
    import subprocess
    import json
    import urllib.request

    from utils.resource_path import get_app_data_path
    model_path = None
    models_dir = get_app_data_path("models/postproc-gguf")

    if os.path.isdir(models_dir):
        for f in os.listdir(models_dir):
            if f.endswith('.gguf'):
                model_path = os.path.join(models_dir, f)
                break

    if not model_path:
        print(f"No GGUF model found in {models_dir}")
        print("Download qwen2.5-0.5b-instruct-q4_k_m.gguf and place it there.")
        return

    # Check for llama-server binary
    server_dir = get_app_data_path("bin")
    server_exe = os.path.join(server_dir, "llama-server.exe")
    if not os.path.isfile(server_exe):
        # Also try llama-server in PATH
        server_exe = "llama-server"

    print(f"Starting llama-server with model {os.path.basename(model_path)}...")

    port = 8787
    proc = subprocess.Popen(
        [server_exe, "-m", model_path, "--port", str(port), "-ngl", "0", "--log-disable"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for server to start
    import time as _time
    for _ in range(30):
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/health")
            resp = urllib.request.urlopen(req, timeout=1)
            if resp.status == 200:
                break
        except Exception:
            _time.sleep(0.5)
    else:
        print("llama-server failed to start within 15s")
        proc.kill()
        return

    print("llama-server ready\n")
    print("--- llama-server Benchmark ---\n")

    for i, text in enumerate(TEST_INPUTS):
        payload = json.dumps({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            "temperature": 0.1,
            "max_tokens": 256,
        }).encode()

        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        t0 = time.perf_counter()
        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read())
        elapsed = time.perf_counter() - t0

        result = data["choices"][0]["message"]["content"]
        tokens = data.get("usage", {}).get("completion_tokens", "?")

        print(f"[{i+1}] {elapsed:.2f}s ({tokens} tokens)")
        print(f"    IN:  {text}")
        print(f"    OUT: {result}")
        print()

    proc.kill()
    proc.wait()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        backend = sys.argv[1]
    else:
        backend = "all"

    if backend in ("onnx", "all"):
        benchmark_onnx()

    if backend in ("llama", "all"):
        benchmark_llama_server()

    if backend not in ("onnx", "llama", "all"):
        print(f"Usage: python {sys.argv[0]} [onnx|llama|all]")
```

**Step 4: Run the ONNX benchmark**

First, download the model:
```bash
huggingface-cli download hazemmabbas/Qwen2.5-0.5B-int4-block-32-acc-3-Instruct-onnx-cpu --local-dir .resonance/models/postproc-onnx
```

Then run:
```bash
python scripts/benchmark_postproc.py onnx
```

Expected: Reports latency per sample, tokens/second, and output quality.

**Step 5: Run the llama-server benchmark**

Download the GGUF model:
```bash
huggingface-cli download Qwen/Qwen2.5-0.5B-Instruct-GGUF qwen2.5-0.5b-instruct-q4_k_m.gguf --local-dir .resonance/models/postproc-gguf
```

Download llama-server from https://github.com/ggml-org/llama.cpp/releases (latest `llama-*-bin-win-cpu-x64.zip`), extract `llama-server.exe` to `.resonance/bin/`.

Then run:
```bash
python scripts/benchmark_postproc.py llama
```

Expected: Reports latency per sample and output quality.

**Step 6: Commit**

```bash
git add pyproject.toml scripts/benchmark_postproc.py
git commit -m "feat: add post-processing benchmark script for onnx and llama-server"
```

---

### Task 2: Evaluate benchmark results and choose default backend

**No code changes.** Review the benchmark output from Task 1 and decide:

- If ONNX is under ~2s per sample with good quality -> use ONNX as default
- If ONNX is too slow but llama-server is fast -> use llama-server as default
- If both are acceptable -> use ONNX (simpler, no subprocess management)

Document the decision in a comment before proceeding to Task 3.

---

### Task 3: Create PostProcessor class with ONNX backend

**Files:**
- Create: `src/core/post_processor.py`
- Create: `tests/core/test_post_processor.py`

**Step 1: Write the failing test**

Create `tests/core/test_post_processor.py`:

```python
"""Tests for PostProcessor."""

import pytest
from unittest.mock import patch, MagicMock


class TestPostProcessorInit:
    def test_default_backend_is_onnx(self):
        from core.post_processor import PostProcessor
        pp = PostProcessor()
        assert pp.backend == "onnx"

    def test_custom_backend(self):
        from core.post_processor import PostProcessor
        pp = PostProcessor(backend="llama-server")
        assert pp.backend == "llama-server"

    def test_model_not_loaded_initially(self):
        from core.post_processor import PostProcessor
        pp = PostProcessor()
        assert not pp.is_loaded()


class TestPostProcessorProcess:
    def test_returns_empty_for_empty_input(self):
        from core.post_processor import PostProcessor
        pp = PostProcessor()
        assert pp.process("") == ""

    def test_returns_input_when_model_not_available(self):
        """If model can't load, return the original text unchanged."""
        from core.post_processor import PostProcessor
        pp = PostProcessor()
        # Don't load any model -- process should return input as-is
        result = pp.process("hello world")
        assert result == "hello world"
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/core/test_post_processor.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'core.post_processor'`

**Step 3: Write the PostProcessor class**

Create `src/core/post_processor.py`:

```python
"""
Local LLM post-processor for transcription cleanup.
Fixes punctuation, capitalization, grammar, and interprets spoken formatting commands.
"""

import os
import threading

from utils.resource_path import get_app_data_path
from utils.logger import get_logger

SYSTEM_PROMPT = (
    "You are a transcription post-processor. Fix grammar, punctuation, and "
    "capitalization. Interpret spoken formatting commands:\n"
    "- 'new line' / 'next line' -> insert a line break\n"
    "- 'bullet' / 'bullets' -> markdown bullet list\n"
    "- 'number one ... number two ...' -> numbered list\n"
    "- 'scratch that' / 'delete that' -> remove preceding content\n"
    "- 'period' / 'comma' / 'colon' -> insert punctuation\n"
    "Output only the corrected text. No explanations."
)


class PostProcessor:
    """Local LLM post-processor for transcription cleanup and formatting."""

    def __init__(self, backend="onnx"):
        self.backend = backend
        self.logger = get_logger()
        self._model = None
        self._tokenizer = None
        self._lock = threading.Lock()
        self._server_proc = None

        if backend == "onnx":
            self._model_dir = get_app_data_path("models/postproc-onnx")
        elif backend == "llama-server":
            self._model_dir = get_app_data_path("models/postproc-gguf")
            self._server_port = 8787
        else:
            raise ValueError(f"Unknown backend: {backend}")

    def is_loaded(self):
        """Check if the model/server is ready."""
        if self.backend == "onnx":
            return self._model is not None
        elif self.backend == "llama-server":
            return self._server_proc is not None and self._server_proc.poll() is None

    def is_model_downloaded(self):
        """Check if model files exist locally."""
        if not os.path.isdir(self._model_dir):
            return False

        if self.backend == "onnx":
            return any(
                f.endswith('.onnx') or f.endswith('.onnx_data')
                for f in os.listdir(self._model_dir)
                if os.path.isfile(os.path.join(self._model_dir, f))
            )
        elif self.backend == "llama-server":
            return any(
                f.endswith('.gguf')
                for f in os.listdir(self._model_dir)
            )

    def load_model(self):
        """Load the model (lazy, thread-safe)."""
        with self._lock:
            if self.is_loaded():
                return

            if not self.is_model_downloaded():
                self.logger.warning("Post-processing model not downloaded")
                return

            if self.backend == "onnx":
                self._load_onnx()
            elif self.backend == "llama-server":
                self._start_llama_server()

    def _load_onnx(self):
        """Load onnxruntime-genai model."""
        try:
            import onnxruntime_genai as og

            self.logger.info(f"Loading ONNX post-processing model from {self._model_dir}...")
            self._model = og.Model(self._model_dir)
            self._tokenizer = og.Tokenizer(self._model)
            self.logger.info("ONNX post-processing model loaded")
        except ImportError:
            self.logger.error("onnxruntime-genai not installed")
        except Exception as e:
            self.logger.error(f"Failed to load ONNX model: {e}", exc_info=True)

    def _start_llama_server(self):
        """Start llama-server as a background process."""
        import subprocess

        server_exe = os.path.join(get_app_data_path("bin"), "llama-server.exe")
        if not os.path.isfile(server_exe):
            self.logger.error(f"llama-server not found at {server_exe}")
            return

        gguf_path = None
        for f in os.listdir(self._model_dir):
            if f.endswith('.gguf'):
                gguf_path = os.path.join(self._model_dir, f)
                break

        if not gguf_path:
            self.logger.error("No GGUF model file found")
            return

        try:
            self.logger.info(f"Starting llama-server on port {self._server_port}...")
            self._server_proc = subprocess.Popen(
                [server_exe, "-m", gguf_path, "--port", str(self._server_port),
                 "-ngl", "0", "--log-disable"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            # Wait for server health
            import time
            import urllib.request
            for _ in range(30):
                try:
                    req = urllib.request.Request(f"http://127.0.0.1:{self._server_port}/health")
                    resp = urllib.request.urlopen(req, timeout=1)
                    if resp.status == 200:
                        self.logger.info("llama-server ready")
                        return
                except Exception:
                    time.sleep(0.5)

            self.logger.error("llama-server failed to start within 15s")
            self._server_proc.kill()
            self._server_proc = None
        except Exception as e:
            self.logger.error(f"Failed to start llama-server: {e}", exc_info=True)

    def process(self, text):
        """
        Post-process transcribed text.

        Args:
            text: Raw transcribed text from Whisper

        Returns:
            Corrected text, or original text if processing fails
        """
        if not text or not text.strip():
            return ""

        if not self.is_loaded():
            self.load_model()
            if not self.is_loaded():
                return text  # Can't load model, return as-is

        try:
            if self.backend == "onnx":
                return self._process_onnx(text)
            elif self.backend == "llama-server":
                return self._process_llama_server(text)
        except Exception as e:
            self.logger.error(f"Post-processing failed: {e}", exc_info=True)
            return text

    def _process_onnx(self, text):
        """Process text using onnxruntime-genai."""
        import onnxruntime_genai as og

        prompt = (
            f"<|im_start|>system\n{SYSTEM_PROMPT}<|im_end|>\n"
            f"<|im_start|>user\n{text}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )

        params = og.GeneratorParams(self._model)
        params.set_search_options(max_length=256, temperature=0.1)
        params.input_ids = self._tokenizer.encode(prompt)

        generator = og.Generator(self._model, params)
        output_tokens = []
        while not generator.is_done():
            generator.compute_logits()
            generator.generate_next_token()
            output_tokens.append(generator.get_next_tokens()[0])

        result = self._tokenizer.decode(output_tokens).strip()
        self.logger.info(f"Post-processed: '{text}' -> '{result}'")
        return result if result else text

    def _process_llama_server(self, text):
        """Process text using llama-server HTTP API."""
        import json
        import urllib.request

        payload = json.dumps({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            "temperature": 0.1,
            "max_tokens": 256,
        }).encode()

        req = urllib.request.Request(
            f"http://127.0.0.1:{self._server_port}/v1/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read())
        result = data["choices"][0]["message"]["content"].strip()

        self.logger.info(f"Post-processed: '{text}' -> '{result}'")
        return result if result else text

    def shutdown(self):
        """Clean up resources."""
        if self._server_proc is not None:
            self.logger.info("Shutting down llama-server...")
            self._server_proc.kill()
            self._server_proc.wait()
            self._server_proc = None
        self._model = None
        self._tokenizer = None
```

**Step 4: Run tests**

Run: `cd src && python -m pytest ../tests/core/test_post_processor.py -v`

Expected: All 4 tests PASS.

**Step 5: Commit**

```bash
git add src/core/post_processor.py tests/core/test_post_processor.py
git commit -m "feat: add PostProcessor class with onnx and llama-server backends"
```

---

### Task 4: Add post-processing config to ConfigManager

**Files:**
- Modify: `src/utils/config.py` — add `get_post_processing_enabled()`, `set_post_processing_enabled()`, `get_post_processing_backend()`

**Step 1: Write the failing test**

Create `tests/utils/test_config_postproc.py`:

```python
"""Tests for post-processing config settings."""

import json
import os
import tempfile
import pytest


class TestPostProcessingConfig:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        # Patch get_app_data_path to use temp dir
        import utils.config as config_mod
        self._orig = config_mod.get_app_data_path
        config_mod.get_app_data_path = lambda *a, **kw: self.tmpdir

        from utils.config import ConfigManager
        self.config = ConfigManager()

    def teardown_method(self):
        import utils.config as config_mod
        config_mod.get_app_data_path = self._orig

    def test_post_processing_disabled_by_default(self):
        assert self.config.get_post_processing_enabled() is False

    def test_set_post_processing_enabled(self):
        self.config.set_post_processing_enabled(True)
        assert self.config.get_post_processing_enabled() is True

    def test_default_backend_is_onnx(self):
        assert self.config.get_post_processing_backend() == "onnx"

    def test_set_backend(self):
        self.config.set_post_processing_backend("llama-server")
        assert self.config.get_post_processing_backend() == "llama-server"
```

**Step 2: Run test to verify it fails**

Run: `cd src && python -m pytest ../tests/utils/test_config_postproc.py -v`

Expected: FAIL with `AttributeError: 'ConfigManager' object has no attribute 'get_post_processing_enabled'`

**Step 3: Add config methods**

In `src/utils/config.py`, add after the `set_device` method (around line 206):

```python
    def get_post_processing_enabled(self):
        """Get whether post-processing is enabled."""
        return self.get("post_processing", "enabled", default=False)

    def set_post_processing_enabled(self, enabled):
        """Set whether post-processing is enabled."""
        self.set("post_processing", "enabled", value=enabled)

    def get_post_processing_backend(self):
        """Get post-processing backend ('onnx' or 'llama-server')."""
        return self.get("post_processing", "backend", default="onnx")

    def set_post_processing_backend(self, backend):
        """Set post-processing backend."""
        self.set("post_processing", "backend", value=backend)
```

**Step 4: Run test**

Run: `cd src && python -m pytest ../tests/utils/test_config_postproc.py -v`

Expected: All 4 tests PASS.

**Step 5: Commit**

```bash
git add src/utils/config.py tests/utils/test_config_postproc.py
git commit -m "feat: add post-processing config settings"
```

---

### Task 5: Wire PostProcessor into the transcription pipeline

**Files:**
- Modify: `src/main.py:33-57` — update `TranscriptionWorker` to accept and call `PostProcessor`
- Modify: `src/main.py:60-98` — update `VTTApplication.__init__` to create `PostProcessor`
- Modify: `src/main.py:457-477` — update `on_settings_changed` to toggle post-processing

**Step 1: Update TranscriptionWorker to accept PostProcessor**

In `src/main.py`, modify the `TranscriptionWorker` class:

```python
class TranscriptionWorker(QObject):
    """Worker for running transcription in background thread."""

    finished = Signal(str)  # Emits transcribed text
    error = Signal(str)  # Emits error message

    def __init__(self, transcriber, audio_data, post_processor=None, logger=None):
        super().__init__()
        self.transcriber = transcriber
        self.audio_data = audio_data
        self.post_processor = post_processor
        self.logger = logger

    def run(self):
        """Run transcription and optional post-processing."""
        try:
            if self.logger:
                self.logger.info("Starting transcription...")
            text = self.transcriber.transcribe(self.audio_data)
            if self.logger:
                self.logger.info(f"Transcription finished, got {len(text)} characters")

            if text and self.post_processor:
                if self.logger:
                    self.logger.info("Running post-processing...")
                text = self.post_processor.process(text)
                if self.logger:
                    self.logger.info(f"Post-processing finished, got {len(text)} characters")

            self.finished.emit(text)
        except Exception as e:
            if self.logger:
                self.logger.error(f"Transcription failed: {e}")
            self.error.emit(str(e))
```

**Step 2: Create PostProcessor in VTTApplication.__init__**

In `src/main.py`, add import at top:

```python
from core.post_processor import PostProcessor
```

In `VTTApplication.__init__`, after the transcriber init (around line 75), add:

```python
        self.post_processor = None
        if self.config.get_post_processing_enabled():
            self.post_processor = PostProcessor(
                backend=self.config.get_post_processing_backend()
            )
```

**Step 3: Pass PostProcessor to TranscriptionWorker**

In `start_transcription` method (around line 191), update the worker creation:

```python
        self.transcription_worker = TranscriptionWorker(
            self.transcriber, audio_data, self.post_processor, self.logger
        )
```

**Step 4: Handle post-processing toggle in on_settings_changed**

In `on_settings_changed` (around line 472), add after the model size check:

```python
        # Update post-processing
        pp_enabled = self.config.get_post_processing_enabled()
        if pp_enabled and self.post_processor is None:
            self.post_processor = PostProcessor(
                backend=self.config.get_post_processing_backend()
            )
        elif not pp_enabled and self.post_processor is not None:
            self.post_processor.shutdown()
            self.post_processor = None
```

**Step 5: Add cleanup in quit method**

In `VTTApplication.quit()` (around line 487), add before `QApplication.quit()`:

```python
        if self.post_processor:
            self.post_processor.shutdown()
```

**Step 6: Commit**

```bash
git add src/main.py
git commit -m "feat: wire PostProcessor into transcription pipeline"
```

---

### Task 6: Add post-processing toggle to Settings UI

**Files:**
- Modify: `src/gui/settings_dialog.py` — add post-processing group with enable toggle

**Step 1: Add the UI group**

In `settings_dialog.py`, in `init_ui()`, add after the dictionary group (around line 227):

```python
        # Post-processing settings
        postproc_group = self.create_postproc_group()
        layout.addWidget(postproc_group)
```

**Step 2: Create the group method**

Add after `create_dictionary_group()`:

```python
    def create_postproc_group(self):
        """Create post-processing configuration group."""
        group = QGroupBox("Post-Processing (Experimental)")
        layout = QVBoxLayout()

        # Enable checkbox
        from PySide6.QtWidgets import QCheckBox
        self.postproc_enabled = QCheckBox("Enable AI post-processing")
        self.postproc_enabled.setToolTip(
            "Uses a small local AI model to fix punctuation, grammar, "
            "and interpret formatting commands after transcription."
        )
        layout.addWidget(self.postproc_enabled)

        # Info
        info_label = QLabel(
            "Cleans up punctuation, capitalization, and handles spoken commands\n"
            "like 'new line', 'bullet', 'scratch that'. Requires ~350MB model download."
        )
        info_label.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(info_label)

        group.setLayout(layout)
        return group
```

**Step 3: Load setting in load_current_settings**

In `load_current_settings()`, add:

```python
        # Post-processing
        self.postproc_enabled.setChecked(self.config.get_post_processing_enabled())
```

**Step 4: Save setting in save_settings**

In `save_settings()`, before `self.config.save()`, add:

```python
            self.config.set_post_processing_enabled(self.postproc_enabled.isChecked())
```

**Step 5: Commit**

```bash
git add src/gui/settings_dialog.py
git commit -m "feat: add post-processing toggle to settings UI"
```

---

### Task 7: Add model download support

**Files:**
- Modify: `src/core/post_processor.py` — add `download_model()` method
- Modify: `src/gui/settings_dialog.py` — add download button and progress

**Step 1: Add download_model to PostProcessor**

In `src/core/post_processor.py`, add method:

```python
    def download_model(self, progress_callback=None):
        """
        Download the post-processing model.

        Args:
            progress_callback: Optional callable(status_text) for progress updates.
        """
        os.makedirs(self._model_dir, exist_ok=True)

        if self.backend == "onnx":
            self._download_onnx_model(progress_callback)
        elif self.backend == "llama-server":
            self._download_gguf_model(progress_callback)

    def _download_onnx_model(self, progress_callback=None):
        """Download ONNX model from HuggingFace."""
        from huggingface_hub import snapshot_download

        if progress_callback:
            progress_callback("Downloading ONNX model...")

        self.logger.info("Downloading ONNX post-processing model...")
        snapshot_download(
            repo_id="hazemmabbas/Qwen2.5-0.5B-int4-block-32-acc-3-Instruct-onnx-cpu",
            local_dir=self._model_dir,
        )
        self.logger.info("ONNX model downloaded")

        if progress_callback:
            progress_callback("Download complete")

    def _download_gguf_model(self, progress_callback=None):
        """Download GGUF model from HuggingFace."""
        from huggingface_hub import hf_hub_download

        if progress_callback:
            progress_callback("Downloading GGUF model...")

        self.logger.info("Downloading GGUF post-processing model...")
        hf_hub_download(
            repo_id="Qwen/Qwen2.5-0.5B-Instruct-GGUF",
            filename="qwen2.5-0.5b-instruct-q4_k_m.gguf",
            local_dir=self._model_dir,
        )
        self.logger.info("GGUF model downloaded")

        if progress_callback:
            progress_callback("Download complete")
```

**Step 2: Add download button to settings UI**

In the `create_postproc_group` method, after the info label, add:

```python
        # Download button
        download_layout = QHBoxLayout()

        self.postproc_status_label = QLabel("")
        self.postproc_status_label.setStyleSheet("font-size: 10px;")
        download_layout.addWidget(self.postproc_status_label)

        download_layout.addStretch()

        self.postproc_download_button = QPushButton("Download Model")
        self.postproc_download_button.clicked.connect(self._download_postproc_model)
        download_layout.addWidget(self.postproc_download_button)

        layout.addLayout(download_layout)
```

Update the `load_current_settings` to show model status:

```python
        # Post-processing model status
        from core.post_processor import PostProcessor
        pp = PostProcessor(backend=self.config.get_post_processing_backend())
        if pp.is_model_downloaded():
            self.postproc_status_label.setText("Model downloaded")
            self.postproc_status_label.setStyleSheet("color: green; font-size: 10px;")
            self.postproc_download_button.setEnabled(False)
        else:
            self.postproc_status_label.setText("Model not downloaded")
            self.postproc_status_label.setStyleSheet("color: orange; font-size: 10px;")
```

Add the download handler:

```python
    def _download_postproc_model(self):
        """Download the post-processing model."""
        from core.post_processor import PostProcessor

        self.postproc_download_button.setEnabled(False)
        self.postproc_status_label.setText("Downloading...")
        self.postproc_status_label.setStyleSheet("color: blue; font-size: 10px;")

        # Force UI update
        QApplication.processEvents()

        try:
            pp = PostProcessor(backend=self.config.get_post_processing_backend())
            pp.download_model(
                progress_callback=lambda s: (
                    self.postproc_status_label.setText(s),
                    QApplication.processEvents()
                )
            )
            self.postproc_status_label.setText("Model downloaded")
            self.postproc_status_label.setStyleSheet("color: green; font-size: 10px;")
        except Exception as e:
            self.postproc_status_label.setText(f"Download failed: {e}")
            self.postproc_status_label.setStyleSheet("color: red; font-size: 10px;")
            self.postproc_download_button.setEnabled(True)
```

Add `QApplication` import if not already present at top of file.

**Step 3: Commit**

```bash
git add src/core/post_processor.py src/gui/settings_dialog.py
git commit -m "feat: add post-processing model download support"
```

---

### Task 8: End-to-end test and polish

**Files:**
- All modified files from previous tasks

**Step 1: Run all tests**

```bash
cd src && python -m pytest ../tests/ -v
```

Expected: All tests pass.

**Step 2: Manual end-to-end test**

1. Start the app: `python src/main.py`
2. Open Settings -> Enable post-processing -> Download Model
3. Save settings
4. Record a short dictation: "hello how are you new line this is a test bullet first item bullet second item"
5. Verify output has proper formatting

**Step 3: Final commit**

```bash
git add -A
git commit -m "feat: complete post-processing integration with onnx and llama-server backends"
```
