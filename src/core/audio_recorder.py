"""
Audio recording module using sounddevice.
Records audio from microphone and provides NumPy array output for Whisper.
"""

import sounddevice as sd
import numpy as np
import queue
import threading


class AudioRecorder:
    """Records audio from microphone using sounddevice."""

    def __init__(self, sample_rate=16000, channels=1):
        """
        Initialize audio recorder.

        Args:
            sample_rate: Sample rate in Hz (16000 is Whisper's native rate)
            channels: Number of audio channels (1 for mono, 2 for stereo)
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.audio_queue = queue.Queue()
        self.recording = False
        self.stream = None
        self.device = None  # None = use default device

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

        Returns:
            List of (index, name) tuples for input devices
        """
        devices = []
        for i, device in enumerate(sd.query_devices()):
            if device['max_input_channels'] > 0:
                devices.append((i, device['name']))
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
                print(f"Audio recording status: {status}")
            if self.recording:
                self.audio_queue.put(indata.copy())

        try:
            self.stream = sd.InputStream(
                device=self.device,
                samplerate=self.sample_rate,
                channels=self.channels,
                callback=callback,
                dtype='float32'
            )
            self.stream.start()
        except Exception as e:
            self.recording = False
            raise Exception(f"Failed to start audio recording: {e}")

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

            return audio_data

        return None

    def is_recording(self):
        """Check if currently recording."""
        return self.recording

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
