"""
Audio recording module using sounddevice.
Records audio from microphone and provides NumPy array output for Whisper.
"""

import sounddevice as sd
import numpy as np
import queue
import threading

from utils.logger import get_logger


class AudioRecorder:
    """Records audio from microphone using sounddevice."""

    def __init__(self, sample_rate=16000, channels=1):
        """
        Initialize audio recorder.

        Args:
            sample_rate: Sample rate in Hz (16000 is Whisper's native rate)
            channels: Number of audio channels (1 for mono, 2 for stereo)
        """
        self.target_sample_rate = sample_rate  # Target rate for Whisper
        self.actual_sample_rate = sample_rate  # Actual device sample rate
        self.channels = channels
        self.audio_queue = queue.Queue()
        self.recording = False
        self.stream = None
        self.device = None  # None = use default device
        self.logger = get_logger()
        self.current_rms = 0.0

    @property
    def sample_rate(self):
        """Backward compatibility property for sample_rate."""
        return self.target_sample_rate

    def set_device(self, device_index):
        """
        Set the audio input device.

        Args:
            device_index: Device index or None for default
        """
        self.device = device_index

    def get_devices(self):
        """
        Get list of available audio input devices.

        Filters to Windows WASAPI devices only (avoids showing the same
        physical device 3-4 times via MME, DirectSound, WDM-KS).
        Falls back to all input devices if WASAPI isn't available.

        Returns:
            List of (index, name) tuples for input devices
        """
        # Find WASAPI host API index
        wasapi_idx = None
        try:
            for i, api in enumerate(sd.query_hostapis()):
                if "WASAPI" in api.get("name", ""):
                    wasapi_idx = i
                    break
        except Exception:
            pass

        devices = []
        seen_names = set()
        for i, device in enumerate(sd.query_devices()):
            if device['max_input_channels'] <= 0:
                continue
            # Filter to WASAPI if available
            if wasapi_idx is not None and device.get('hostapi') != wasapi_idx:
                continue
            # Deduplicate by name
            name = device['name']
            if name in seen_names:
                continue
            seen_names.add(name)
            devices.append((i, name))

        # Fallback: if WASAPI filter returned nothing, show all input devices
        if not devices:
            seen_names.clear()
            for i, device in enumerate(sd.query_devices()):
                if device['max_input_channels'] > 0:
                    name = device['name']
                    if name not in seen_names:
                        seen_names.add(name)
                        devices.append((i, name))

        return devices

    def start_recording(self):
        """Start capturing audio from microphone."""
        if self.recording:
            return

        self.recording = True
        self.audio_queue = queue.Queue()  # Clear previous data

        def callback(indata, frames, time, status):
            """Callback for sounddevice to handle incoming audio data."""
            if status:
                self.logger.warning(f"Audio recording status: {status}")
            if self.recording:
                self.audio_queue.put(indata.copy())
                self.current_rms = float(np.sqrt(np.mean(indata ** 2)))

        # Try sample rates in order: target (16kHz), then fallbacks
        sample_rates = [self.target_sample_rate, 48000, 44100, 32000, 22050]
        last_error = None
        
        for rate in sample_rates:
            try:
                self.stream = sd.InputStream(
                    device=self.device,
                    samplerate=rate,
                    channels=self.channels,
                    callback=callback,
                    dtype='float32'
                )
                self.stream.start()
                self.actual_sample_rate = rate
                if rate != self.target_sample_rate:
                    self.logger.info(
                        f"Audio: using {rate}Hz (device doesn't support {self.target_sample_rate}Hz)"
                    )
                return  # Success!
            except Exception as e:
                last_error = e
                if self.stream:
                    try:
                        self.stream.close()
                    except:
                        pass
                    self.stream = None
                continue
        
        # All rates failed
        self.recording = False
        raise Exception(f"Failed to start audio recording: {last_error}")

    def stop_recording(self):
        """
        Stop recording and return audio data.

        Returns:
            NumPy array of audio samples (float32, shape: (samples, channels))
            Returns None if no audio was recorded
        """
        if not self.recording:
            return None

        self.recording = False
        self.current_rms = 0.0

        # Stop and close the stream
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

        # Collect all audio chunks from queue
        audio_chunks = []
        while not self.audio_queue.empty():
            audio_chunks.append(self.audio_queue.get())

        if audio_chunks:
            # Concatenate all chunks into single array
            audio_data = np.concatenate(audio_chunks, axis=0)

            # Convert to mono if stereo (take mean of channels)
            if audio_data.ndim > 1 and audio_data.shape[1] > 1:
                audio_data = np.mean(audio_data, axis=1)

            # Flatten to 1D array if needed
            if audio_data.ndim > 1:
                audio_data = audio_data.flatten()

            # Resample to target rate if needed
            if self.actual_sample_rate != self.target_sample_rate:
                audio_data = self._resample(audio_data, self.actual_sample_rate, self.target_sample_rate)

            return audio_data

        return None

    def is_recording(self):
        """Check if currently recording."""
        return self.recording

    def _resample(self, audio, from_rate, to_rate):
        """Resample audio from one sample rate to another using numpy interpolation.
        
        Uses linear interpolation which is efficient and good for audio resampling.
        Whisper expects 16kHz, but some devices may provide different sample rates.
        """
        if from_rate == to_rate:
            return audio
        
        # Calculate new length
        ratio = to_rate / from_rate
        new_length = int(len(audio) * ratio)
        
        # Linear interpolation: map old indices to new indices
        old_indices = np.arange(len(audio))
        new_indices = np.linspace(0, len(audio) - 1, new_length)
        
        # Interpolate
        resampled = np.interp(new_indices, old_indices, audio)
        return resampled.astype(np.float32)

    def get_default_device(self):
        """
        Get the default input device.

        Returns:
            Tuple of (device_index, device_name)
        """
        try:
            default_device = sd.query_devices(kind='input')
            return (sd.default.device[0], default_device['name'])
        except Exception:
            return (None, "Unknown")
