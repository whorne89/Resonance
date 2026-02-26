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
