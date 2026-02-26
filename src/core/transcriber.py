"""
Whisper transcription module using faster-whisper.
Provides speech-to-text transcription with optimized performance.
"""

import numpy as np
import threading
import os

# Suppress HuggingFace symlinks warning on Windows
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

from faster_whisper import WhisperModel

from utils.resource_path import get_app_data_path
from utils.logger import get_logger


class Transcriber:
    """Handles Whisper model loading and audio transcription."""

    def __init__(self, model_size="small", device="cpu", compute_type="int8"):
        """
        Initialize transcriber.

        Args:
            model_size: Whisper model size (tiny, base, small, medium, large)
            device: Device to run on ("cpu" or "cuda")
            compute_type: Quantization type ("int8", "float16", "float32")
        """
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.model = None
        self.loading = False
        self._lock = threading.Lock()
        self.logger = get_logger()

        # Set up local model cache directory in user's app data
        # This ensures models persist and are writable even when running as bundled EXE
        self.models_dir = get_app_data_path("models")

        self.logger.info(f"Transcriber initialized, model directory: {self.models_dir}")

    def load_model(self):
        """
        Load the Whisper model (lazy loading).
        This can take a while on first run as it downloads the model.
        """
        with self._lock:
            if self.model is not None or self.loading:
                return

            self.loading = True
            try:
                self.logger.info(f"Loading Whisper model '{self.model_size}' from {self.models_dir}...")
                # Download and load model from HuggingFace
                # Models are cached locally in ~/.resonance/models/
                self.model = WhisperModel(
                    self.model_size,
                    device=self.device,
                    compute_type=self.compute_type,
                    download_root=self.models_dir,
                    local_files_only=False
                )
                self.logger.info(f"Model '{self.model_size}' loaded successfully")
            except Exception as e:
                self.logger.error(f"Error loading model: {e}", exc_info=True)
                raise
            finally:
                self.loading = False

    def change_model(self, model_size):
        """
        Change to a different model size.

        Args:
            model_size: New model size to load
        """
        with self._lock:
            self.model_size = model_size
            self.model = None  # Force reload
        self.load_model()

    def transcribe(self, audio_data, language="en"):
        """
        Transcribe audio data to text.

        Args:
            audio_data: NumPy array of audio samples (float32)
            language: Language code (e.g., "en" for English)

        Returns:
            Transcribed text as string
        """
        # Ensure model is loaded
        if self.model is None:
            self.load_model()

        if audio_data is None or len(audio_data) == 0:
            return ""

        try:
            self.logger.info(f"Starting transcription of {len(audio_data)} samples...")
            # Transcribe with faster-whisper
            # Note: vad_filter disabled for bundled EXE compatibility
            # (VAD requires silero_vad.onnx which isn't easily bundled)
            # beam_size=5 is a good balance of speed and accuracy
            segments, info = self.model.transcribe(
                audio_data,
                language=language,
                beam_size=5,
                vad_filter=False,
            )

            # Combine all segments into single text
            text_parts = []
            for segment in segments:
                text_parts.append(segment.text)

            result = " ".join(text_parts).strip()
            self.logger.info(f"Transcription result: '{result}' ({len(result)} chars)")
            return result

        except Exception as e:
            self.logger.error(f"Transcription error: {e}", exc_info=True)
            return ""

    def is_loaded(self):
        """Check if model is currently loaded."""
        return self.model is not None

    def is_model_downloaded(self, model_size):
        """
        Check if a specific model is already downloaded.

        Args:
            model_size: Size of the model to check (tiny, base, small, medium, large)

        Returns:
            bool: True if model is downloaded, False otherwise
        """
        # Check if the model directory exists
        # faster-whisper uses HuggingFace cache format: models--Systran--faster-whisper-{size}
        model_path = os.path.join(self.models_dir, f"models--Systran--faster-whisper-{model_size}")
        exists = os.path.exists(model_path) and os.path.isdir(model_path)
        self.logger.info(f"Checking model {model_size}: path={model_path}, exists={exists}")
        return exists

    @staticmethod
    def get_model_size_info(model_size):
        """
        Get information about a model size.

        Args:
            model_size: Model size string

        Returns:
            dict: Dictionary with 'size_mb' and 'description' keys
        """
        model_info = {
            "tiny": {"size_mb": 70, "description": "Fastest, lower accuracy"},
            "base": {"size_mb": 140, "description": "Fast, decent accuracy"},
            "small": {"size_mb": 500, "description": "Balanced (recommended)"},
            "medium": {"size_mb": 1500, "description": "Better accuracy"},
            "large": {"size_mb": 3000, "description": "Best accuracy"}
        }
        return model_info.get(model_size, {"size_mb": 0, "description": "Unknown"})

    def get_available_models(self):
        """
        Get list of available Whisper model sizes.

        Returns:
            List of model size strings
        """
        return ["tiny", "base", "small", "medium", "large", "large-v2", "large-v3"]

    def get_model_info(self):
        """
        Get information about current model.

        Returns:
            Dictionary with model information
        """
        return {
            "size": self.model_size,
            "device": self.device,
            "compute_type": self.compute_type,
            "loaded": self.is_loaded()
        }
