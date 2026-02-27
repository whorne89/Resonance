"""
Sound effects for Resonance.
Generates short tones programmatically using numpy + sounddevice.
"""

import numpy as np
import sounddevice as sd
import threading

from utils.logger import get_logger


class SoundEffects:
    """Generates and plays short notification tones."""

    def __init__(self, sample_rate=44100, volume=0.15):
        self.sample_rate = sample_rate
        self.volume = volume
        self.logger = get_logger()

        # Pre-generate tones at init so playback is instant
        self._start_tone = self._generate_sweep(freq_start=880, freq_end=1100, duration=0.15)
        self._stop_tone = self._generate_sweep(freq_start=1100, freq_end=880, duration=0.15)

    def _generate_sweep(self, freq_start, freq_end, duration):
        """Generate a frequency sweep tone with fade in/out envelope."""
        t = np.linspace(0, duration, int(self.sample_rate * duration), endpoint=False)
        freq = np.linspace(freq_start, freq_end, len(t))
        phase = 2 * np.pi * np.cumsum(freq) / self.sample_rate
        tone = np.sin(phase) * self.volume

        # Raised cosine fade in/out (20ms) to avoid clicks
        fade_samples = int(self.sample_rate * 0.02)
        if fade_samples > 0 and len(tone) > 2 * fade_samples:
            fade_in = 0.5 * (1 - np.cos(np.linspace(0, np.pi, fade_samples)))
            fade_out = 0.5 * (1 + np.cos(np.linspace(0, np.pi, fade_samples)))
            tone[:fade_samples] *= fade_in
            tone[-fade_samples:] *= fade_out

        return tone.astype(np.float32)

    def play_start_tone(self):
        """Play ascending tone (recording started). Non-blocking."""
        self._play_async(self._start_tone)

    def play_stop_tone(self):
        """Play descending tone (recording stopped). Non-blocking."""
        self._play_async(self._stop_tone)

    def _play_async(self, tone):
        """Play a tone in a background thread to avoid blocking."""
        def _play():
            try:
                sd.play(tone, samplerate=self.sample_rate, blocking=True)
            except Exception as e:
                self.logger.warning(f"Sound playback failed: {e}")

        thread = threading.Thread(target=_play, daemon=True)
        thread.start()
