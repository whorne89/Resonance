"""
Post-processing module for transcription text cleanup.
Uses a small language model to fix grammar, punctuation, and capitalization,
and interpret spoken formatting commands.
"""

import json
import os
import threading
import time
import subprocess
import urllib.request
import urllib.error

from utils.resource_path import get_app_data_path
from utils.logger import get_logger

# System prompt shared by all backends — few-shot style for 0.5B model
SYSTEM_PROMPT = (
    'You clean up voice-to-text transcriptions. Fix grammar, punctuation, and '
    'capitalization. When the speaker says a formatting command, apply it.\n\n'
    'Commands:\n'
    '- "bullet" before an item = bullet point\n'
    '- "new line" = start a new line\n'
    '- "number one/two/three" before items = numbered list\n'
    '- "scratch that" = delete everything before it\n\n'
    'Input: the weather is nice today\n'
    'Output: The weather is nice today.\n\n'
    'Input: bullet eggs bullet milk bullet bread\n'
    'Output: - Eggs\n- Milk\n- Bread\n\n'
    'Input: dear sarah new line thanks for your help new line best regards tom\n'
    'Output: Dear Sarah,\nThanks for your help.\nBest regards,\nTom\n\n'
    'Input: send me the file new line also check the budget\n'
    'Output: Send me the file.\nAlso, check the budget.\n\n'
    'Input: number one cats number two dogs number three fish\n'
    'Output: 1. Cats\n2. Dogs\n3. Fish\n\n'
    'Input: i want pizza scratch that actually i want pasta\n'
    'Output: Actually, I want pasta.\n\n'
    'Now clean up this transcription. Output the corrected text only:'
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

# ONNX model info
ONNX_REPO_ID = "hazemmabbas/Qwen2.5-0.5B-int4-block-32-acc-3-Instruct-onnx-cpu"


class PostProcessor:
    """
    Post-processes transcription output using a small language model
    to fix grammar, punctuation, capitalization, and formatting commands.
    """

    def __init__(self, backend="llama-server"):
        """
        Initialize post-processor.

        Args:
            backend: Backend to use ("llama-server" or "onnx")
        """
        self.backend = backend
        self.logger = get_logger()
        self._lock = threading.Lock()
        self._loaded = False

        # llama-server backend state
        self._server_process = None

        # onnx backend state
        self._onnx_model = None
        self._onnx_tokenizer = None

        self.logger.info(f"PostProcessor initialized with backend: {self.backend}")

    def is_loaded(self):
        """Check if the post-processing model is currently loaded and ready."""
        return self._loaded

    def is_model_downloaded(self):
        """
        Check if the model files are downloaded for the current backend.

        Returns:
            bool: True if model files exist locally
        """
        if self.backend == "llama-server":
            return self._is_llama_server_downloaded()
        elif self.backend == "onnx":
            return self._is_onnx_downloaded()
        return False

    def load_model(self):
        """
        Load the model (lazy, thread-safe).
        For llama-server: starts the server subprocess.
        For onnx: loads the model into memory.
        """
        with self._lock:
            if self._loaded:
                return

            try:
                if self.backend == "llama-server":
                    self._start_llama_server()
                elif self.backend == "onnx":
                    self._load_onnx_model()
                self._loaded = True
                self.logger.info(f"PostProcessor model loaded (backend={self.backend})")
            except Exception as e:
                self.logger.error(f"Failed to load post-processor model: {e}", exc_info=True)
                self._loaded = False

    def process(self, raw_text):
        """
        Process transcribed text to fix grammar, punctuation, and formatting.

        Args:
            raw_text: Raw transcription text

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
            if self.backend == "llama-server":
                return self._process_llama_server(raw_text)
            elif self.backend == "onnx":
                return self._process_onnx(raw_text)
            else:
                self.logger.warning(f"Unknown backend '{self.backend}', returning text unchanged")
                return raw_text
        except Exception as e:
            self.logger.error(f"Post-processing failed: {e}", exc_info=True)
            return raw_text

    def download_model(self, progress_callback=None):
        """
        Download model files for the current backend.

        Args:
            progress_callback: Optional callback(bytes_downloaded, total_bytes)
                for progress reporting.
        """
        if self.backend == "llama-server":
            self._download_llama_server(progress_callback)
        elif self.backend == "onnx":
            self._download_onnx_model(progress_callback)

    def shutdown(self):
        """Shut down the post-processor and release resources."""
        with self._lock:
            if self.backend == "llama-server":
                self._stop_llama_server()
            elif self.backend == "onnx":
                self._onnx_model = None
                self._onnx_tokenizer = None
            self._loaded = False
            self.logger.info("PostProcessor shut down")

    # -------------------------------------------------------------------------
    # llama-server backend implementation
    # -------------------------------------------------------------------------

    def _get_gguf_dir(self):
        """Get directory for GGUF model files."""
        return get_app_data_path("models/postproc-gguf")

    def _get_bin_dir(self):
        """Get directory for llama-server binary and DLLs."""
        return get_app_data_path("bin")

    def _get_llama_server_exe(self):
        """Get absolute path to llama-server.exe."""
        return os.path.join(self._get_bin_dir(), "llama-server.exe")

    def _get_gguf_model_path(self):
        """Get absolute path to the GGUF model file."""
        return os.path.join(self._get_gguf_dir(), GGUF_FILENAME)

    def _is_llama_server_downloaded(self):
        """Check if llama-server binary and GGUF model are downloaded."""
        exe_path = self._get_llama_server_exe()
        model_path = self._get_gguf_model_path()
        return os.path.isfile(exe_path) and os.path.isfile(model_path)

    def _start_llama_server(self):
        """Start llama-server as a background subprocess."""
        exe_path = self._get_llama_server_exe()
        model_path = self._get_gguf_model_path()

        if not os.path.isfile(exe_path):
            raise FileNotFoundError(f"llama-server.exe not found at: {exe_path}")
        if not os.path.isfile(model_path):
            raise FileNotFoundError(f"GGUF model not found at: {model_path}")

        self.logger.info(f"Starting llama-server: {exe_path}")
        self.logger.info(f"Model: {model_path}")

        # Use absolute paths (Windows requirement)
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
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )

        # Wait for the health endpoint to become available
        self._wait_for_health(timeout=30)
        self.logger.info("llama-server is ready")

    def _wait_for_health(self, timeout=30):
        """Wait for llama-server health endpoint to respond OK."""
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
        """Stop the llama-server subprocess."""
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

    def _process_llama_server(self, text):
        """Send text to llama-server for post-processing via OpenAI-compatible API."""
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

    def _download_llama_server(self, progress_callback=None):
        """Download llama-server binary and GGUF model."""
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
                # Extract llama-server.exe and any DLLs
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

    def _download_file(self, url, dest_path, progress_callback=None):
        """Download a file with optional progress reporting."""
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            chunk_size = 1024 * 1024  # 1 MB chunks

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

    # -------------------------------------------------------------------------
    # onnx backend implementation
    # -------------------------------------------------------------------------

    def _get_onnx_dir(self):
        """Get directory for ONNX model files."""
        return get_app_data_path("models/postproc-onnx")

    def _is_onnx_downloaded(self):
        """Check if ONNX model is downloaded."""
        onnx_dir = self._get_onnx_dir()
        # Check for genai_config.json which is present in downloaded ONNX models
        config_path = os.path.join(onnx_dir, "genai_config.json")
        return os.path.isfile(config_path)

    def _load_onnx_model(self):
        """Load the ONNX model into memory."""
        try:
            import onnxruntime_genai as og
        except ImportError:
            raise ImportError(
                "onnxruntime-genai is required for the onnx backend. "
                "Install it with: uv pip install onnxruntime-genai"
            )

        onnx_dir = self._get_onnx_dir()
        if not self._is_onnx_downloaded():
            raise FileNotFoundError(f"ONNX model not found at: {onnx_dir}")

        self.logger.info(f"Loading ONNX model from {onnx_dir}")
        self._onnx_model = og.Model(onnx_dir)
        self._onnx_tokenizer = og.Tokenizer(self._onnx_model)
        self.logger.info("ONNX model loaded")

    def _process_onnx(self, text):
        """Process text using the ONNX model."""
        import onnxruntime_genai as og

        messages = json.dumps([
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ])
        prompt = self._onnx_tokenizer.apply_chat_template(messages)
        input_tokens = self._onnx_tokenizer.encode(prompt)

        params = og.GeneratorParams(self._onnx_model)
        params.set_search_options(max_length=256, temperature=0.1)

        generator = og.Generator(self._onnx_model, params)
        generator.append_tokens(input_tokens)

        output_tokens = []
        while not generator.is_done():
            generator.generate_next_token()
            output_tokens.append(generator.get_next_tokens()[0])

        result = self._onnx_tokenizer.decode(output_tokens)
        return result.strip()

    def _download_onnx_model(self, progress_callback=None):
        """Download ONNX model from HuggingFace."""
        try:
            from huggingface_hub import snapshot_download
        except ImportError:
            raise ImportError(
                "huggingface_hub is required to download ONNX models. "
                "Install it with: uv pip install huggingface_hub"
            )

        onnx_dir = self._get_onnx_dir()
        self.logger.info(f"Downloading ONNX model to {onnx_dir}")

        snapshot_download(
            repo_id=ONNX_REPO_ID,
            local_dir=onnx_dir,
        )
        self.logger.info("ONNX model download complete")
