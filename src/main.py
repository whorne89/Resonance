"""
Resonance - Voice to Text Application
Main entry point that orchestrates all components.
"""

import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QObject, Signal, QThread, QTimer, Qt

from core.audio_recorder import AudioRecorder
from core.transcriber import Transcriber
from core.keyboard_typer import KeyboardTyper
from core.hotkey_manager import HotkeyManager
from gui.system_tray import SystemTrayIcon
from gui.settings_dialog import SettingsDialog
from utils.config import ConfigManager
from utils.logger import setup_logger


class TranscriptionWorker(QObject):
    """Worker for running transcription in background thread."""

    finished = Signal(str)  # Emits transcribed text
    error = Signal(str)  # Emits error message

    def __init__(self, transcriber, audio_data, logger=None):
        super().__init__()
        self.transcriber = transcriber
        self.audio_data = audio_data
        self.logger = logger

    def run(self):
        """Run transcription."""
        try:
            if self.logger:
                self.logger.info("Starting transcription...")
            text = self.transcriber.transcribe(self.audio_data)
            if self.logger:
                self.logger.info(f"Transcription finished, got {len(text)} characters")
            self.finished.emit(text)
        except Exception as e:
            if self.logger:
                self.logger.error(f"Transcription failed: {e}")
            self.error.emit(str(e))


class VTTApplication(QObject):
    """Main application controller."""

    def __init__(self):
        super().__init__()

        # Initialize logger
        self.logger = setup_logger()
        self.logger.info("Starting Resonance...")

        # Initialize components
        self.config = ConfigManager()
        self.audio_recorder = AudioRecorder()
        self.transcriber = Transcriber(
            model_size=self.config.get_model_size()
        )
        self.keyboard_typer = KeyboardTyper(
            typing_speed=self.config.get_typing_speed(),
            use_clipboard=self.config.get("typing", "use_clipboard_fallback", default=False)
        )
        self.hotkey_manager = HotkeyManager()

        # Set audio device from config
        device_idx = self.config.get_audio_device()
        if device_idx is not None:
            self.audio_recorder.set_device(device_idx)

        # GUI components
        self.tray_icon = None
        self.settings_dialog = None

        # Threading
        self.transcription_thread = None
        self.transcription_worker = None

        # Setup hotkey
        self.setup_hotkey()

        self.logger.info("Application initialized")

    def setup_hotkey(self):
        """Setup global hotkey listener."""
        hotkey = self.config.get_hotkey()
        try:
            self.hotkey_manager.register_hotkey(
                hotkey,
                on_press=self.on_hotkey_press,
                on_release=self.on_hotkey_release
            )
            self.logger.info(f"Hotkey registered: {hotkey}")
        except Exception as e:
            self.logger.error(f"Failed to register hotkey: {e}")
            if self.tray_icon:
                self.tray_icon.show_error(f"Failed to register hotkey: {e}")

    def on_hotkey_press(self):
        """Called when hotkey is pressed - start recording."""
        try:
            self.logger.info("Hotkey pressed - starting recording")
            self.audio_recorder.start_recording()

            # Update UI
            if self.tray_icon:
                self.tray_icon.set_recording_state()

        except Exception as e:
            self.logger.error(f"Failed to start recording: {e}")
            if self.tray_icon:
                self.tray_icon.show_error(f"Recording failed: {e}")

    def on_hotkey_release(self):
        """Called when hotkey is released - stop recording and transcribe."""
        try:
            self.logger.info("Hotkey released - stopping recording")

            # Stop recording and get audio data
            audio_data = self.audio_recorder.stop_recording()

            if audio_data is None or len(audio_data) == 0:
                self.logger.warning("No audio data recorded")
                if self.tray_icon:
                    self.tray_icon.set_idle_state()
                return

            self.logger.info(f"Audio recorded: {len(audio_data)} samples")

            # Update UI to transcribing state
            if self.tray_icon:
                self.tray_icon.set_transcribing_state()

            # Run transcription in background thread
            self.start_transcription(audio_data)

        except Exception as e:
            self.logger.error(f"Failed to process recording: {e}")
            if self.tray_icon:
                self.tray_icon.show_error(f"Processing failed: {e}")
                self.tray_icon.set_idle_state()

    def start_transcription(self, audio_data):
        """
        Start transcription in background thread.

        Args:
            audio_data: NumPy array of audio samples
        """
        # Check if transcription is already running
        if self.transcription_thread is not None:
            is_running = self.transcription_thread.isRunning()
            self.logger.info(f"Previous thread exists, isRunning={is_running}")
            if is_running:
                self.logger.warning("Transcription already in progress, skipping...")
                if self.tray_icon:
                    self.tray_icon.show_error("Please wait for previous transcription to finish")
                    self.tray_icon.set_idle_state()
                return

        # Clean up any previous thread
        if self.transcription_thread is not None:
            self.logger.info("Cleaning up previous thread before starting new one")
            self.transcription_thread.quit()
            self.transcription_thread.wait()
            self.transcription_thread.deleteLater()
            self.transcription_thread = None

        if self.transcription_worker is not None:
            self.transcription_worker.deleteLater()
            self.transcription_worker = None

        # Create worker and thread
        self.transcription_thread = QThread()
        self.transcription_worker = TranscriptionWorker(self.transcriber, audio_data, self.logger)

        # Move worker to thread
        self.transcription_worker.moveToThread(self.transcription_thread)

        # Connect signals
        self.transcription_thread.started.connect(self.transcription_worker.run)
        self.transcription_worker.finished.connect(self.on_transcription_complete)
        self.transcription_worker.error.connect(self.on_transcription_error)

        # CRITICAL: Quit and cleanup must happen BEFORE the completion handlers
        # Otherwise the typing in the completion handler can block the event loop
        self.transcription_worker.finished.connect(lambda: self._quit_transcription_thread())
        self.transcription_worker.error.connect(lambda: self._quit_transcription_thread())

        # Start thread
        self.transcription_thread.start()

        # Fallback: ensure cleanup happens even if signals fail
        # Schedule cleanup for 30 seconds after start as safety net
        QTimer.singleShot(30000, self.force_cleanup_if_stuck)

    def on_transcription_complete(self, text):
        """
        Called when transcription is complete.

        Args:
            text: Transcribed text
        """
        self.logger.info(f"Transcription complete: '{text}'")

        try:
            # Type the text
            if text:
                try:
                    self.logger.info("Starting text output...")
                    # Run typing with error handling
                    success = self.keyboard_typer.type_text(text)
                    if success:
                        self.logger.info("Text output successful")
                    else:
                        self.logger.warning("Text output failed")

                    # Note: Transcription complete notifications are disabled
                except Exception as e:
                    self.logger.error(f"Error outputting text: {e}")
                    if self.tray_icon:
                        self.tray_icon.show_error(f"Failed to paste text: {e}")
            else:
                self.logger.warning("Transcription returned empty text")

            # Reset UI
            if self.tray_icon:
                self.tray_icon.set_idle_state()
        finally:
            # Always ensure cleanup happens even if there's an exception
            self.logger.info("Transcription complete handler finished, cleanup will occur via signal")

    def on_transcription_error(self, error_msg):
        """
        Called when transcription fails.

        Args:
            error_msg: Error message
        """
        self.logger.error(f"Transcription error: {error_msg}")

        try:
            if self.tray_icon:
                self.tray_icon.show_error(f"Transcription failed: {error_msg}")
                self.tray_icon.set_idle_state()
        finally:
            # Always ensure cleanup happens even if there's an exception
            self.logger.info("Transcription error handler finished, cleanup will occur via signal")

    def _quit_transcription_thread(self):
        """Immediately quit and cleanup the transcription thread."""
        self.logger.info("Quitting transcription thread")
        if self.transcription_thread:
            self.transcription_thread.quit()
            # Use QTimer to cleanup shortly after quit
            QTimer.singleShot(100, self.cleanup_transcription_thread)

    def cleanup_transcription_thread(self):
        """Clean up transcription thread resources."""
        self.logger.info("Cleaning up transcription thread")
        if self.transcription_thread:
            if self.transcription_thread.isRunning():
                self.logger.warning("Thread still running during cleanup, waiting...")
                self.transcription_thread.wait(2000)
            self.transcription_thread.deleteLater()
            self.transcription_thread = None
        if self.transcription_worker:
            self.transcription_worker.deleteLater()
            self.transcription_worker = None
        self.logger.info("Transcription thread cleanup complete")

    def force_cleanup_if_stuck(self):
        """Force cleanup if thread is still running after timeout (safety net)."""
        if self.transcription_thread is not None:
            if self.transcription_thread.isRunning():
                self.logger.warning("Transcription thread still running after timeout - forcing cleanup")
                self.transcription_thread.quit()
                self.transcription_thread.wait(1000)  # Wait up to 1 second
            self.cleanup_transcription_thread()

    def show_settings(self):
        """Show settings dialog."""
        self.logger.info("Settings dialog requested")
        try:
            # Always create a fresh dialog to ensure it appears
            self.logger.info("Creating new settings dialog")
            dialog = SettingsDialog(
                self.config,
                self.audio_recorder,
                self.transcriber
            )
            dialog.settings_changed.connect(self.on_settings_changed)

            # Set window flags to ensure it appears on top
            dialog.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint)

            self.logger.info("Showing settings dialog as modal")
            # Use exec_() to show as modal dialog - this FORCES it to appear
            dialog.exec_()

        except Exception as e:
            self.logger.error(f"Failed to show settings dialog: {e}")
            if self.tray_icon:
                self.tray_icon.show_error(f"Failed to open settings: {e}")

    def on_settings_changed(self):
        """Handle settings changes."""
        self.logger.info("Settings changed - applying updates")

        # Reload hotkey
        self.hotkey_manager.unregister_hotkey()
        self.setup_hotkey()

        # Update audio device
        device_idx = self.config.get_audio_device()
        self.audio_recorder.set_device(device_idx)

        # Update model (will reload on next transcription)
        model_size = self.config.get_model_size()
        if model_size != self.transcriber.model_size:
            self.transcriber.change_model(model_size)

        # Update typing speed and method
        self.keyboard_typer.set_typing_speed(self.config.get_typing_speed())
        use_clipboard = self.config.get("typing", "use_clipboard_fallback", default=False)
        self.keyboard_typer.use_clipboard = use_clipboard

    def quit(self):
        """Quit application."""
        self.logger.info("Shutting down...")

        # Unregister hotkey
        self.hotkey_manager.unregister_hotkey()

        # Stop recording if active
        if self.audio_recorder.is_recording():
            self.audio_recorder.stop_recording()

        # Quit application
        QApplication.quit()


def main():
    """Main entry point."""
    app = QApplication(sys.argv)
    app.setApplicationName("Resonance")
    app.setApplicationDisplayName("Resonance")
    app.setQuitOnLastWindowClosed(False)  # Keep running with system tray

    # Create application controller
    vtt_app = VTTApplication()

    # Create and setup system tray with formatted hotkey
    tray_icon = SystemTrayIcon(hotkey_display=vtt_app.config.get_hotkey_display())
    vtt_app.tray_icon = tray_icon

    # Connect tray signals
    tray_icon.settings_requested.connect(vtt_app.show_settings)
    tray_icon.quit_requested.connect(vtt_app.quit)

    # Show ready message
    tray_icon.show_message(
        "Resonance Service Started",
        f"To start dictation, press {vtt_app.config.get_hotkey_display()}"
    )

    # Run application
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
