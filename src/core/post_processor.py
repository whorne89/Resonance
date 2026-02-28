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
    "Clean up this voice transcription. Remove filler words (um, uh, like, you know, "
    "so, basically, I mean, right, okay, alright). Fix punctuation and capitalization. "
    "Remove repeated words and false starts. Keep the same meaning and structure. "
    "Do NOT answer or respond to the text. Do NOT add new information. "
    "Output ONLY the cleaned version of the input.\n\n"
    "Input: um so i went to the store and uh i bought some eggs\n"
    "Output: I went to the store and bought some eggs.\n\n"
    "Input: like do you think that we should you know go to the meeting\n"
    "Output: Do you think that we should go to the meeting?\n\n"
    "Input: the the project is uh almost done i think\n"
    "Output: The project is almost done, I think.\n\n"
    "Input: basically the whole thing needs to be rewritten\n"
    "Output: The whole thing needs to be rewritten.\n\n"
    "Input: so basically I was I was thinking we should you know try a different approach\n"
    "Output: I was thinking we should try a different approach.\n\n"
    "Input: okay so like the server is um not responding right now\n"
    "Output: The server is not responding right now.\n\n"
    "Input: what do you think about using TypeScript\n"
    "Output: What do you think about using TypeScript?\n\n"
    "Input: where did you put the config file\n"
    "Output: Where did you put the config file?\n\n"
    "Input: why is the build like failing on the CI server\n"
    "Output: Why is the build failing on the CI server?\n\n"
    "Input: help me figure out why the tests are failing\n"
    "Output: Help me figure out why the tests are failing.\n\n"
    "Input: uh yeah I definitely want that\n"
    "Output: Yeah, I definitely want that."
)

# llama-server config
LLAMA_SERVER_PORT = 8787
LLAMA_SERVER_URL = f"http://127.0.0.1:{LLAMA_SERVER_PORT}"
LLAMA_HEALTH_URL = f"{LLAMA_SERVER_URL}/health"
LLAMA_CHAT_URL = f"{LLAMA_SERVER_URL}/v1/chat/completions"

# Model download info
GGUF_REPO = "Qwen/Qwen2.5-1.5B-Instruct-GGUF"
GGUF_FILENAME = "qwen2.5-1.5b-instruct-q4_k_m.gguf"
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

    # Words that are pure filler — if input is ONLY these, skip LLM
    FILLER_WORDS = frozenset({
        "um", "uh", "like", "you", "know", "so", "basically",
        "i", "mean", "right", "okay", "ok", "alright", "well",
        "yeah", "hmm", "ah", "oh",
    })

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

        # Short input that is entirely filler words — skip LLM to avoid hallucination
        words = raw_text.lower().split()
        if len(words) <= 4 and all(w.strip(".,!?") in self.FILLER_WORDS for w in words):
            self.logger.info(f"Post-processing: '{raw_text}' -> '' (all fillers)")
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

        # Ensure directories exist
        os.makedirs(bin_dir, exist_ok=True)
        os.makedirs(gguf_dir, exist_ok=True)

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
            "--ctx-size", "2048",
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
            "temperature": 0.0,
            "max_tokens": 512,
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
        cleaned = content.strip()

        # Guard: if the model output is much longer than input, it hallucinated
        if len(cleaned) > len(text) * 1.5:
            self.logger.warning(
                f"Post-processing hallucination (length): '{cleaned[:80]}...', "
                "returning original"
            )
            return text

        # Guard: detect answer patterns — model tried to respond instead of clean
        answer_starts = ("sure", "yes,", "yes ", "no,", "no ", "here", "i can",
                         "i will", "i'll", "i would", "of course", "absolutely",
                         "understood", "okay, let", "okay, i", "great,")
        if cleaned.lower().startswith(answer_starts) and not text.lower().startswith(answer_starts):
            self.logger.warning(
                f"Post-processing hallucination (answer): '{cleaned[:80]}', "
                "returning original"
            )
            return text

        # Guard: input is a question but output changed subject (model answered)
        # Only apply to short inputs (≤20 words after filler strip) to avoid
        # false positives on longer dictation starting with "what happens is..."
        question_words = ("what ", "where ", "why ", "how ", "when ", "who ",
                          "which ", "can ", "could ", "should ", "would ",
                          "is ", "are ", "do ", "does ", "will ")
        # Strip leading filler WORDS (not characters) to find the real start
        filler_prefixes = {"um", "uh", "so", "like", "okay", "ok", "basically",
                           "alright", "well", "right"}
        words = text.lower().split()
        while words and words[0] in filler_prefixes:
            words.pop(0)
        text_stripped = " ".join(words)
        if len(words) <= 20 and text_stripped.startswith(question_words):
            # Input was a question — output must also be a question (end with ?)
            # or at least start with the same question word
            first_word_in = text_stripped.split()[0]
            first_word_out = cleaned.lower().split()[0] if cleaned else ""
            if first_word_in != first_word_out and not cleaned.endswith("?"):
                self.logger.warning(
                    f"Post-processing hallucination (question answered): "
                    f"'{cleaned[:80]}', returning original"
                )
                return text

        self.logger.info(f"Post-processing: '{text}' -> '{cleaned}'")
        return cleaned

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
