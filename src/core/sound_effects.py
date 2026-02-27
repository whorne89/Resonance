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

        # C5 (warm-bright) for start, G4 (warm-low) for stop — perfect 5th.
        self._start_path = os.path.join(self._temp_dir, 'start.wav')
        self._stop_path = os.path.join(self._temp_dir, 'stop.wav')

        self._write_wav(self._start_path, self._generate_warm_tone(freq=523, duration=0.35))
        self._write_wav(self._stop_path, self._generate_warm_tone(freq=392, duration=0.35))

    def _generate_warm_tone(self, freq, duration):
        """Generate a warm synth pad tone with soft attack and release.

        Uses detuned harmonics for chorus-like width, and a smooth
        attack-sustain-release envelope for that analog synth character.
        """
        sr = self.sample_rate
        n_samples = int(sr * duration)
        t = np.linspace(0, duration, n_samples, endpoint=False)

        # Warm pad: fundamental + slightly detuned harmonics for width
        tone = np.sin(2 * np.pi * freq * t)
        tone += 0.45 * np.sin(2 * np.pi * freq * 2.003 * t)   # detuned octave
        tone += 0.20 * np.sin(2 * np.pi * freq * 2.999 * t)   # detuned 12th
        tone += 0.10 * np.sin(2 * np.pi * freq * 4.002 * t)   # detuned 2nd octave

        # Normalize then apply volume
        peak = np.max(np.abs(tone))
        if peak > 0:
            tone = tone / peak * self.volume

        # ASR envelope: soft attack, brief sustain, gentle release
        attack_n = int(sr * 0.025)    # 25ms
        sustain_n = int(sr * 0.10)    # 100ms
        release_n = n_samples - attack_n - sustain_n

        envelope = np.concatenate([
            0.5 * (1 - np.cos(np.linspace(0, np.pi, attack_n))),
            np.ones(sustain_n),
            0.5 * (1 + np.cos(np.linspace(0, np.pi, max(1, release_n)))),
        ])[:n_samples]

        tone *= envelope
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
