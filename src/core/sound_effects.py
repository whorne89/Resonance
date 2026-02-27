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
        self._start_wav = self._make_wav(self._generate_tone(freq=880, duration=0.25))
        self._stop_wav = self._make_wav(self._generate_tone(freq=660, duration=0.25))

    def _generate_tone(self, freq, duration):
        """Generate a clean sine tone with smooth raised-cosine envelope."""
        n_samples = int(self.sample_rate * duration)
        t = np.linspace(0, duration, n_samples, endpoint=False)

        # Pure sine wave
        tone = np.sin(2 * np.pi * freq * t) * self.volume

        # Raised-cosine fade in (15ms) and fade out (80ms) for clean transients
        fade_in = int(self.sample_rate * 0.015)
        fade_out = int(self.sample_rate * 0.08)

        envelope = np.ones(n_samples)
        if fade_in > 0:
            envelope[:fade_in] = 0.5 * (1 - np.cos(np.linspace(0, np.pi, fade_in)))
        if fade_out > 0:
            envelope[-fade_out:] = 0.5 * (1 + np.cos(np.linspace(0, np.pi, fade_out)))

        tone *= envelope
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
