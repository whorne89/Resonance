"""
Sound effects for Resonance.
Generates short tones programmatically using numpy + sounddevice.
"""

import numpy as np
import sounddevice as sd

from utils.logger import get_logger


class SoundEffects:
    """Generates and plays short notification tones."""

    def __init__(self, sample_rate=44100, volume=0.15):
        self.sample_rate = sample_rate
        self.volume = volume
        self.logger = get_logger()

        # Pre-generate tones at init so playback is instant.
        # C6 (bright) for start, G5 (warm) for stop — a perfect 4th apart.
        self._start_tone = self._generate_chime(freq=1047, duration=0.15)
        self._stop_tone = self._generate_chime(freq=784, duration=0.15)

    def _generate_chime(self, freq, duration):
        """Generate a chime tone with harmonics, chorus, and natural decay."""
        t = np.linspace(0, duration, int(self.sample_rate * duration), endpoint=False)

        # Fundamental + slight detune for chorus width + octave harmonic
        tone = np.sin(2 * np.pi * freq * t)
        tone += 0.3 * np.sin(2 * np.pi * (freq * 1.005) * t)
        tone += 0.4 * np.sin(2 * np.pi * freq * 2 * t)

        # Normalize then apply volume
        peak = np.max(np.abs(tone))
        if peak > 0:
            tone = tone / peak * self.volume

        # Exponential decay for natural chime character
        tone *= np.exp(-t * 18)

        # Quick fade in (2ms) to avoid click on attack
        fade_samples = int(self.sample_rate * 0.002)
        if fade_samples > 0:
            tone[:fade_samples] *= np.linspace(0, 1, fade_samples)

        return tone.astype(np.float32)

    def play_start_tone(self):
        """Play chime (recording started). Blocks until complete (~150ms)."""
        self._play(self._start_tone)

    def play_stop_tone(self):
        """Play chime (recording stopped). Blocks until complete (~150ms)."""
        self._play(self._stop_tone)

    def _play(self, tone):
        """Play a tone synchronously. Blocks until playback completes."""
        try:
            sd.play(tone, samplerate=self.sample_rate)
            sd.wait()
        except Exception as e:
            self.logger.warning(f"Sound playback failed: {e}")
