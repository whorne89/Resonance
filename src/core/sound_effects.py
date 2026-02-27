"""
Sound effects for Resonance.
Generates short tones as WAV files and plays via Windows native audio API.
Uses SND_FILENAME | SND_ASYNC for reliable non-blocking playback that
doesn't conflict with sounddevice recording.
"""

import os
import struct
import tempfile
import numpy as np
import winsound

from utils.logger import get_logger


class SoundEffects:
    """Generates and plays short notification tones."""

    def __init__(self, sample_rate=44100, volume=0.3):
        self.sample_rate = sample_rate
        self.volume = volume
        self.logger = get_logger()

        # Write tones as WAV files — winsound needs SND_FILENAME for async.
        self._temp_dir = tempfile.mkdtemp(prefix='resonance_')

        # A5 (bright) for start, E5 (warm) for stop — a perfect 4th apart.
        self._start_path = os.path.join(self._temp_dir, 'start.wav')
        self._stop_path = os.path.join(self._temp_dir, 'stop.wav')

        self._write_wav(self._start_path, self._generate_chime(freq=880, duration=0.35))
        self._write_wav(self._stop_path, self._generate_chime(freq=659, duration=0.35))

    def _generate_chime(self, freq, duration):
        """Generate a resonant chime with harmonics and natural decay.

        Uses fundamental + perfect fifth + octave + 12th for a bell-like
        timbre that fits the 'Resonance' character.
        """
        t = np.linspace(0, duration, int(self.sample_rate * duration), endpoint=False)

        # Partials: fundamental, perfect 5th, octave, 12th
        tone = np.sin(2 * np.pi * freq * t)
        tone += 0.35 * np.sin(2 * np.pi * freq * 1.5 * t)
        tone += 0.20 * np.sin(2 * np.pi * freq * 2.0 * t)
        tone += 0.10 * np.sin(2 * np.pi * freq * 3.0 * t)

        # Normalize then apply volume
        peak = np.max(np.abs(tone))
        if peak > 0:
            tone = tone / peak * self.volume

        # Exponential decay — struck bell character
        tone *= np.exp(-t * 10)

        # Smooth raised-cosine fade in (5ms) to avoid click
        fade_in = int(self.sample_rate * 0.005)
        if fade_in > 0:
            tone[:fade_in] *= 0.5 * (1 - np.cos(np.linspace(0, np.pi, fade_in)))

        return tone

    def _write_wav(self, path, tone):
        """Write tone data to a 16-bit mono WAV file."""
        pcm = np.clip(tone * 32767, -32768, 32767).astype(np.int16)
        data_size = len(pcm) * 2

        with open(path, 'wb') as f:
            f.write(b'RIFF')
            f.write(struct.pack('<I', 36 + data_size))
            f.write(b'WAVE')
            f.write(b'fmt ')
            f.write(struct.pack('<I', 16))
            f.write(struct.pack('<H', 1))                    # PCM format
            f.write(struct.pack('<H', 1))                    # mono
            f.write(struct.pack('<I', self.sample_rate))     # sample rate
            f.write(struct.pack('<I', self.sample_rate * 2)) # byte rate
            f.write(struct.pack('<H', 2))                    # block align
            f.write(struct.pack('<H', 16))                   # bits per sample
            f.write(b'data')
            f.write(struct.pack('<I', data_size))
            f.write(pcm.tobytes())

    def play_start_tone(self):
        """Play chime (recording started). Non-blocking."""
        try:
            winsound.PlaySound(
                self._start_path,
                winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT
            )
        except Exception as e:
            self.logger.warning(f"Sound playback failed: {e}")

    def play_stop_tone(self):
        """Play chime (recording stopped). Non-blocking."""
        try:
            winsound.PlaySound(
                self._stop_path,
                winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT
            )
        except Exception as e:
            self.logger.warning(f"Sound playback failed: {e}")
