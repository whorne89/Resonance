"""
Whisper transcription module using faster-whisper.
Provides speech-to-text transcription with optimized performance.
"""

import math
import os
import shutil
import threading

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

    def change_device(self, device):
        """
        Change processing device and reload model.

        Args:
            device: 'cpu' or 'cuda'
        """
        with self._lock:
            self.device = device
            self.model = None  # Force reload
        self.load_model()

    def transcribe(self, audio_data, language="en", initial_prompt=None):
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
            self.last_confidence = 0.0
            return ""

        try:
            self.logger.info(f"Starting transcription of {len(audio_data)} samples...")
            segments, info = self.model.transcribe(
                audio_data,
                language=language,
                beam_size=5,
                vad_filter=False,
                initial_prompt=initial_prompt,
            )

            # Combine all segments into single text
            text_parts = []
            logprobs = []
            for segment in segments:
                text_parts.append(segment.text)
                logprobs.append(segment.avg_logprob)

            result = " ".join(text_parts).strip()

            # Convert avg log probability to 0-100% confidence
            if logprobs:
                avg_logprob = sum(logprobs) / len(logprobs)
                self.last_confidence = min(1.0, math.exp(avg_logprob))
            else:
                self.last_confidence = 0.0

            self.logger.info(f"Transcription result: '{result}' ({len(result)} chars, "
                             f"confidence={self.last_confidence:.0%})")
            return result

        except Exception as e:
            self.logger.error(f"Transcription error: {e}", exc_info=True)
            return ""

    def is_loaded(self):
        """Check if model is currently loaded."""
        return self.model is not None

    def clean_partial_download(self, model_size):
        """
        Remove partially downloaded model files so a fresh download can succeed.

        Checks for .incomplete files in blobs/ or missing model.bin in snapshots/.
        If partial state is found, removes the entire model cache directory.

        Args:
            model_size: Model ID — short name or full HuggingFace repo ID.

        Returns:
            bool: True if a partial download was cleaned up, False otherwise.
        """
        if '/' in model_size:
            cache_name = "models--" + model_size.replace('/', '--')
        else:
            cache_name = f"models--Systran--faster-whisper-{model_size}"
        model_path = os.path.join(self.models_dir, cache_name)

        if not os.path.isdir(model_path):
            return False

        # Check for .incomplete files in blobs/
        blobs_dir = os.path.join(model_path, "blobs")
        has_incomplete = False
        if os.path.isdir(blobs_dir):
            for fname in os.listdir(blobs_dir):
                if fname.endswith(".incomplete"):
                    has_incomplete = True
                    break

        # Check that at least one snapshot has a model.bin
        has_model_bin = False
        snapshots_dir = os.path.join(model_path, "snapshots")
        if os.path.isdir(snapshots_dir):
            for snap in os.listdir(snapshots_dir):
                if os.path.isfile(os.path.join(snapshots_dir, snap, "model.bin")):
                    has_model_bin = True
                    break

        # Directory exists but is in a partial state
        if has_incomplete or (os.path.isdir(snapshots_dir) and not has_model_bin):
            self.logger.info(f"Cleaning partial download for {model_size}: "
                             f"incomplete={has_incomplete}, model_bin={has_model_bin}")
            try:
                shutil.rmtree(model_path)
                self.logger.info(f"Removed partial download directory: {model_path}")
                return True
            except Exception as e:
                self.logger.error(f"Failed to clean partial download: {e}")
                return False

        return False

    def is_model_downloaded(self, model_size):
        """
        Check if a specific model is already downloaded.

        Args:
            model_size: Model ID — either a short name ("small") or a full
                HuggingFace repo ID ("Systran/faster-distil-whisper-large-v3").

        Returns:
            bool: True if model is fully downloaded, False otherwise
        """
        if '/' in model_size:
            cache_name = "models--" + model_size.replace('/', '--')
        else:
            cache_name = f"models--Systran--faster-whisper-{model_size}"
        model_path = os.path.join(self.models_dir, cache_name)

        if not os.path.isdir(model_path):
            self.logger.info(f"Checking model {model_size}: path={model_path}, not found")
            return False

        # Check for .incomplete files in blobs — indicates a partial download
        blobs_dir = os.path.join(model_path, "blobs")
        if os.path.isdir(blobs_dir):
            for fname in os.listdir(blobs_dir):
                if fname.endswith(".incomplete"):
                    self.logger.info(f"Checking model {model_size}: incomplete download detected")
                    return False

        # Check that at least one snapshot has a model.bin file
        snapshots_dir = os.path.join(model_path, "snapshots")
        if os.path.isdir(snapshots_dir):
            for snap in os.listdir(snapshots_dir):
                model_bin = os.path.join(snapshots_dir, snap, "model.bin")
                if os.path.isfile(model_bin):
                    self.logger.info(f"Checking model {model_size}: fully downloaded")
                    return True

        self.logger.info(f"Checking model {model_size}: directory exists but model files missing")
        return False

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
            "small": {"size_mb": 500, "description": "Balanced"},
            "medium": {"size_mb": 1500, "description": "High accuracy, slower"},
            "Systran/faster-distil-whisper-large-v3": {"size_mb": 800, "description": "High accuracy, ~6x faster than large"},
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
