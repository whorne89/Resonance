"""
Sound effects for Resonance.
Generates short tones and plays them via Windows native audio API (winsound).
Uses a completely separate audio path from sounddevice to avoid conflicts
with the recording InputStream.
"""

import io
import struct
import numpy as np
import winsound

from utils.logger import get_logger


class SoundEffects:
    """Generates and plays short notification tones."""

    def __init__(self, sample_rate=44100, volume=0.25):
        self.sample_rate = sample_rate
        self.volume = volume
        self.logger = get_logger()

        # Pre-generate tones as in-memory WAV bytes for instant playback.
        # C6 (bright) for start, G5 (warm) for stop — a perfect 4th apart.
        self._start_wav = self._make_wav(self._generate_chime(freq=1047, duration=0.18))
        self._stop_wav = self._make_wav(self._generate_chime(freq=784, duration=0.18))

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
        tone *= np.exp(-t * 12)

        # Quick fade in (2ms) to avoid click on attack
        fade_samples = int(self.sample_rate * 0.002)
        if fade_samples > 0:
            tone[:fade_samples] *= np.linspace(0, 1, fade_samples)

        return tone

    def _make_wav(self, tone):
        """Convert float32 tone array to in-memory WAV bytes."""
        pcm = (tone * 32767).astype(np.int16)
        data_size = len(pcm) * 2

        buf = io.BytesIO()
        buf.write(b'RIFF')
        buf.write(struct.pack('<I', 36 + data_size))
        buf.write(b'WAVE')
        buf.write(b'fmt ')
        buf.write(struct.pack('<I', 16))
        buf.write(struct.pack('<H', 1))                    # PCM format
        buf.write(struct.pack('<H', 1))                    # mono
        buf.write(struct.pack('<I', self.sample_rate))     # sample rate
        buf.write(struct.pack('<I', self.sample_rate * 2)) # byte rate
        buf.write(struct.pack('<H', 2))                    # block align
        buf.write(struct.pack('<H', 16))                   # bits per sample
        buf.write(b'data')
        buf.write(struct.pack('<I', data_size))
        buf.write(pcm.tobytes())

        return buf.getvalue()

    def play_start_tone(self):
        """Play chime (recording started). Non-blocking."""
        try:
            winsound.PlaySound(self._start_wav, winsound.SND_MEMORY | winsound.SND_ASYNC)
        except Exception as e:
            self.logger.warning(f"Sound playback failed: {e}")

    def play_stop_tone(self):
        """Play chime (recording stopped). Non-blocking."""
        try:
            winsound.PlaySound(self._stop_wav, winsound.SND_MEMORY | winsound.SND_ASYNC)
        except Exception as e:
            self.logger.warning(f"Sound playback failed: {e}")
