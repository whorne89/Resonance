"""
Sound effects for Resonance.
Generates short tones as WAV files and plays via Windows native audio API.
Uses SND_FILENAME | SND_ASYNC for reliable non-blocking playback that
doesn't conflict with sounddevice recording.

Custom sounds: Drop your own start.wav / stop.wav into .resonance/sounds/
to override the generated defaults.
"""

import os
import struct
import numpy as np
import winsound

from utils.logger import get_logger
from utils.resource_path import get_app_data_path


class SoundEffects:
    """Generates and plays short notification tones."""

    def __init__(self, sample_rate=44100, volume=0.3):
        self.sample_rate = sample_rate
        self.volume = volume
        self.logger = get_logger()

        # Sound files live in .resonance/sounds/
        sounds_dir = get_app_data_path("sounds")

        self._start_path = os.path.join(sounds_dir, 'start.wav')
        self._stop_path = os.path.join(sounds_dir, 'stop.wav')

        # Only generate defaults if user hasn't provided custom WAV files
        if not os.path.exists(self._start_path):
            self._write_wav(self._start_path, self._generate_start_chime())
        if not os.path.exists(self._stop_path):
            self._write_wav(self._stop_path, self._generate_stop_chime())

    def _generate_single_note(self, freq, duration):
        """Generate a single piano note (no reverb).

        Models piano string physics: sharp hammer attack, harmonics with
        inharmonicity, and per-partial decay rates.
        """
        sr = self.sample_rate
        n = int(sr * duration)
        t = np.linspace(0, duration, n, endpoint=False)

        inharmonicity = 0.0004
        partials = [
            (1, 1.00, 5),
            (2, 0.65, 7),
            (3, 0.35, 9),
            (4, 0.20, 12),
            (5, 0.12, 15),
            (6, 0.06, 18),
        ]

        tone = np.zeros(n)
        for h, amp, decay in partials:
            f = h * freq * np.sqrt(1 + inharmonicity * h * h)
            tone += amp * np.sin(2 * np.pi * f * t) * np.exp(-t * decay)

        # Sharp attack (3ms) — hammer strike
        attack = int(sr * 0.003)
        if attack > 0:
            tone[:attack] *= np.linspace(0, 1, attack)

        # Normalize to unit peak
        peak = np.max(np.abs(tone))
        if peak > 0:
            tone /= peak

        return tone

    def _apply_reverb(self, signal):
        """Apply room reverb via early reflections."""
        n = len(signal)
        sr = self.sample_rate
        output = signal.copy()

        reflections = [
            (0.035, 0.22),   # 35ms — first wall
            (0.070, 0.15),   # 70ms — opposite wall
            (0.120, 0.09),   # 120ms — room fill
            (0.185, 0.05),   # 185ms — reverb tail
        ]
        for delay_s, amp in reflections:
            d = int(sr * delay_s)
            if d < n:
                output[d:] += signal[:n - d] * amp

        return output

    def _generate_start_chime(self):
        """Three ascending piano notes — Xbox guide-style activation chime.

        C4 → E4 → G4 (major triad), each note overlapping the previous
        as it decays, creating a cascading resonant effect.
        """
        sr = self.sample_rate
        spacing = 0.12     # 120ms between note starts
        note_dur = 0.45    # each note rings for 450ms
        total = spacing * 2 + note_dur
        n_samples = int(sr * total)

        # C4 → E4 → G4 ascending major triad
        freqs = [261.6, 329.6, 392.0]
        output = np.zeros(n_samples)

        for i, freq in enumerate(freqs):
            offset = int(sr * spacing * i)
            note = self._generate_single_note(freq, note_dur)
            end = min(offset + len(note), n_samples)
            output[offset:end] += note[:end - offset]

        # Normalize, apply reverb, then final volume
        peak = np.max(np.abs(output))
        if peak > 0:
            output /= peak

        output = self._apply_reverb(output)

        peak = np.max(np.abs(output))
        if peak > 0:
            output = output / peak * self.volume

        return output

    def _generate_stop_chime(self):
        """Single low piano note — warm, resolving stop indicator."""
        note = self._generate_single_note(freq=261.6, duration=0.5)  # C4
        note = self._apply_reverb(note)

        peak = np.max(np.abs(note))
        if peak > 0:
            note = note / peak * self.volume

        return note

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
