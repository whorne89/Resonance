"""
Whisper transcription module using faster-whisper.
Provides speech-to-text transcription with optimized performance.
"""

from faster_whisper import WhisperModel
import numpy as np
import threading
import os


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

        # Set up local model cache directory
        # Get the directory where this script is located at runtime
        # Use __file__ to get the actual location of this transcriber.py file
        this_file = os.path.abspath(__file__)
        # Go up two directories: transcriber.py -> core -> src
        src_dir = os.path.dirname(os.path.dirname(this_file))
        self.models_dir = os.path.join(src_dir, "models")

        print(f"Transcriber model directory: {self.models_dir}")

        # Create models directory if it doesn't exist
        if not os.path.exists(self.models_dir):
            os.makedirs(self.models_dir)

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
                print(f"Loading Whisper model '{self.model_size}'...")
                # Download and load model from HuggingFace
                # Models are cached locally in src/models/
                self.model = WhisperModel(
                    self.model_size,
                    device=self.device,
                    compute_type=self.compute_type,
                    download_root=self.models_dir,
                    local_files_only=False
                )
                print(f"Model '{self.model_size}' loaded successfully")
            except Exception as e:
                print(f"Error loading model: {e}")
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
            # Transcribe with faster-whisper
            # vad_filter=True uses Voice Activity Detection to filter silence
            # beam_size=5 is a good balance of speed and accuracy
            segments, info = self.model.transcribe(
                audio_data,
                language=language,
                beam_size=5,
                vad_filter=True,
                vad_parameters=dict(
                    min_silence_duration_ms=500  # Minimum silence duration
                )
            )

            # Combine all segments into single text
            text_parts = []
            for segment in segments:
                text_parts.append(segment.text)

            result = " ".join(text_parts).strip()
            return result

        except Exception as e:
            print(f"Transcription error: {e}")
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
        print(f"Checking model {model_size}: path={model_path}, exists={exists}")
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
