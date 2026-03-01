"""
Resonance - Voice to Text Application
Main entry point that orchestrates all components.
"""

import sys
import ctypes
from datetime import date
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QObject, Signal, QThread, QTimer, Qt


def set_windows_app_id():
    """Set Windows AppUserModelID for proper taskbar/tray display."""
    try:
        # This tells Windows to display "Resonance" instead of the exe name
        app_id = "Resonance.VoiceToText.1.0"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass  # Not on Windows or API not available

from core.audio_recorder import AudioRecorder
from core.transcriber import Transcriber
from core.keyboard_typer import KeyboardTyper
from core.hotkey_manager import HotkeyManager
from core.dictionary import DictionaryProcessor
from core.post_processor import PostProcessor
from core.sound_effects import SoundEffects
from core.screen_context import ScreenContextEngine
from gui.recording_overlay import RecordingOverlay
from gui.system_tray import SystemTrayIcon
from gui.settings_dialog import SettingsDialog
from gui.theme import apply_theme
from gui.toast_notification import ClipboardToast, DownloadToast
from utils.config import ConfigManager
from utils.logger import setup_logger


class TranscriptionWorker(QObject):
    """Worker for running transcription in background thread."""

    finished = Signal(str)  # Emits transcribed text
    error = Signal(str)  # Emits error message

    def __init__(self, transcriber, audio_data, post_processor=None, logger=None, ocr_context=None):
        super().__init__()
        self.transcriber = transcriber
        self.audio_data = audio_data
        self.post_processor = post_processor
        self.logger = logger
        self.ocr_context = ocr_context

    def run(self):
        """Run transcription."""
        try:
            # Build OCR-derived hints if available
            initial_prompt = None
            system_prompt = None
            if self.ocr_context:
                initial_prompt = ScreenContextEngine.build_whisper_prompt(
                    self.ocr_context.proper_nouns, self.ocr_context.app_type
                )
                system_prompt = ScreenContextEngine.build_system_prompt(
                    self.ocr_context.app_type, self.ocr_context.proper_nouns
                )
                if self.logger:
                    self.logger.info(f"OCR context: app_type={self.ocr_context.app_type.value}, "
                                    f"nouns={self.ocr_context.proper_nouns}")

            if self.logger:
                self.logger.info("Starting transcription...")
            text = self.transcriber.transcribe(self.audio_data, initial_prompt=initial_prompt)
            if self.logger:
                self.logger.info(f"Transcription finished, got {len(text)} characters")

            if text and self.post_processor:
                if self.logger:
                    self.logger.info("Running post-processing...")
                text = self.post_processor.process(text, system_prompt=system_prompt)
                if self.logger:
                    self.logger.info(f"Post-processing finished, got {len(text)} characters")

            # Apply structural formatting based on app type
            if self.ocr_context and text:
                from core.screen_context import AppType
                if self.ocr_context.app_type == AppType.CHAT:
                    text = ScreenContextEngine.apply_chat_formatting(text)

            self.finished.emit(text)
        except Exception as e:
            if self.logger:
                self.logger.error(f"Transcription failed: {e}")
            self.error.emit(str(e))


class ModelLoadWorker(QObject):
    """Worker for loading/downloading a Whisper model in the background."""

    finished = Signal()
    error = Signal(str)

    def __init__(self, transcriber):
        super().__init__()
        self.transcriber = transcriber

    def run(self):
        try:
            self.transcriber.load_model()
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))


class VTTApplication(QObject):
    """Main application controller."""

    # Signals for thread-safe hotkey handling.
    # Hotkey callbacks fire from background threads — these signals
    # marshal execution to the main Qt thread via QueuedConnection.
    _hotkey_pressed = Signal()
    _hotkey_released = Signal()

    def __init__(self):
        super().__init__()

        # Initialize logger
        self.logger = setup_logger()
        self.logger.info("Starting Resonance...")

        # Initialize components
        self.config = ConfigManager()
        self.audio_recorder = AudioRecorder()
        self.transcriber = Transcriber(
            model_size=self.config.get_model_size(),
        )
        self.keyboard_typer = KeyboardTyper(
            typing_speed=self.config.get_typing_speed(),
            use_clipboard=self.config.get("typing", "use_clipboard_fallback", default=False)
        )
        self.keyboard_typer.on_tick = lambda: QApplication.processEvents()
        self.hotkey_manager = HotkeyManager()
        self.dictionary = DictionaryProcessor(self.config, self.logger)
        self.sound_effects = SoundEffects()

        self.post_processor = None
        if self.config.get_post_processing_enabled():
            self.post_processor = PostProcessor()

        # Screen context (OCR) — requires post-processing
        self.screen_context = None
        if self.config.get_ocr_enabled() and self.post_processor is not None:
            self.screen_context = ScreenContextEngine()
        self._current_ocr_context = None

        # Set audio device from config
        device_idx = self.config.get_audio_device()
        if device_idx is not None:
            self.audio_recorder.set_device(device_idx)

        # GUI components
        self.tray_icon = None
        self.settings_dialog = None
        self.overlay = None  # Created in main() after QApplication exists
        self.clipboard_toast = None  # Created in main() after QApplication exists

        # Threading
        self.transcription_thread = None
        self.transcription_worker = None
        self._last_audio_samples = 0  # Track sample count for stats

        # Connect hotkey signals to handlers (thread-safe marshaling)
        self._hotkey_pressed.connect(self.on_hotkey_press)
        self._hotkey_released.connect(self.on_hotkey_release)

        # Setup hotkey
        self.setup_hotkey()

        self.logger.info("Application initialized")

    def setup_hotkey(self):
        """Setup global hotkey listener."""
        hotkey = self.config.get_hotkey()
        try:
            self.hotkey_manager.register_hotkey(
                hotkey,
                on_press=self._hotkey_pressed.emit,
                on_release=self._hotkey_released.emit
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

            # Play start tone before recording to avoid capturing it
            self.sound_effects.play_start_tone()

            self.audio_recorder.start_recording()

            # Fire OCR capture in background (non-blocking, runs during recording)
            if self.screen_context:
                import threading
                def _capture_ocr():
                    try:
                        self._current_ocr_context = self.screen_context.capture()
                    except Exception as e:
                        self.logger.warning(f"OCR capture failed: {e}")
                        self._current_ocr_context = None
                threading.Thread(target=_capture_ocr, daemon=True).start()
            else:
                self._current_ocr_context = None

            # Update UI
            if self.tray_icon:
                self.tray_icon.set_recording_state()
            if self.overlay:
                self.overlay.show_recording()

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

            # Play stop tone
            self.sound_effects.play_stop_tone()

            if audio_data is None or len(audio_data) == 0:
                self.logger.warning("No audio data recorded")
                if self.tray_icon:
                    self.tray_icon.set_idle_state()
                if self.overlay:
                    self.overlay.hide_overlay()
                return

            self.logger.info(f"Audio recorded: {len(audio_data)} samples")
            self._last_audio_samples = len(audio_data)

            # Update UI to transcribing state
            if self.tray_icon:
                self.tray_icon.set_transcribing_state()
            if self.overlay:
                self.overlay.show_processing()

            # Run transcription in background thread
            self.start_transcription(audio_data)

        except Exception as e:
            self.logger.error(f"Failed to process recording: {e}")
            if self.tray_icon:
                self.tray_icon.show_error(f"Processing failed: {e}")
                self.tray_icon.set_idle_state()
            if self.overlay:
                self.overlay.hide_overlay()

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
                if self.overlay:
                    self.overlay.hide_overlay()
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
        self.transcription_worker = TranscriptionWorker(
            self.transcriber, audio_data, self.post_processor, self.logger,
            ocr_context=self._current_ocr_context
        )

        # Move worker to thread
        self.transcription_worker.moveToThread(self.transcription_thread)

        # Connect signals
        self.transcription_thread.started.connect(self.transcription_worker.run)
        self.transcription_worker.finished.connect(self.on_transcription_complete)
        self.transcription_worker.error.connect(self.on_transcription_error)

        # Cleanup must happen after completion/error handlers finish.
        # Use QueuedConnection to ensure these run on the main thread (not the worker thread),
        # which avoids "QObject::startTimer: Timers can only be used with threads started with QThread".
        self.transcription_worker.finished.connect(
            self._quit_transcription_thread, Qt.ConnectionType.QueuedConnection
        )
        self.transcription_worker.error.connect(
            self._quit_transcription_thread, Qt.ConnectionType.QueuedConnection
        )

        # Start thread
        self.transcription_thread.start()

    def on_transcription_complete(self, text):
        """
        Called when transcription is complete.

        Args:
            text: Transcribed text
        """
        self.logger.info(f"Transcription complete: '{text}'")

        try:
            # Apply custom dictionary replacements
            if text:
                original = text
                text = self.dictionary.apply(text)
                if text != original:
                    self.logger.info(f"Dictionary applied: '{original}' -> '{text}'")

            # Update usage statistics
            if text:
                self._update_statistics(text)

            # Type the text
            if text:
                try:
                    self.logger.info("Starting text output...")
                    # Show typing state on overlay for char-by-char mode
                    if not self.keyboard_typer.use_clipboard and self.overlay:
                        self.overlay.show_typing()
                        QApplication.processEvents()  # Repaint before blocking type loop
                    # Run typing with error handling
                    success = self.keyboard_typer.type_text(text)
                    if success:
                        self.logger.info("Text output successful")
                        # Show green completion state on overlay
                        if self.overlay:
                            if self.keyboard_typer.use_clipboard:
                                self.overlay.show_pasted()
                            else:
                                self.overlay.show_complete()
                            QApplication.processEvents()
                    else:
                        self.logger.warning("Text output failed")
                except Exception as e:
                    self.logger.error(f"Error outputting text: {e}")
                    if self.tray_icon:
                        self.tray_icon.show_error(f"Failed to paste text: {e}")
            else:
                self.logger.warning("Transcription returned empty text")
                if self.overlay:
                    self.overlay.show_no_speech()

            # Reset UI
            if self.tray_icon:
                self.tray_icon.set_idle_state()
            if self.overlay:
                # Brief hold before fading out
                self.overlay.hide_overlay(delay_ms=600)
        finally:
            # Always ensure cleanup happens even if there's an exception
            self.logger.info("Transcription complete handler finished, cleanup will occur via signal")

    def _update_statistics(self, text):
        """Update usage statistics after a successful transcription."""
        try:
            word_count = len(text.split())
            char_count = len(text)

            self.config.increment_stat("total_words", word_count)
            self.config.increment_stat("total_transcriptions", 1)
            self.config.increment_stat("total_characters", char_count)

            # Set first_used if not already set
            stats = self.config.get_statistics()
            if not stats.get("first_used"):
                stats["first_used"] = date.today().isoformat()
                self.config.set("statistics", value=stats)

            # Recording duration from audio samples
            sample_rate = self.config.get("audio", "sample_rate", default=16000)
            if self._last_audio_samples > 0:
                duration = self._last_audio_samples / sample_rate
                self.config.increment_stat("total_recording_seconds", round(duration, 1))

            self.config.save()
        except Exception as e:
            self.logger.error(f"Failed to update statistics: {e}")

    def on_transcription_error(self, error_msg):
        """
        Called when transcription fails.

        Args:
            error_msg: Error message
        """
        self.logger.error(f"Transcription error: {error_msg}")

        try:
            if self.overlay:
                self.overlay.hide_overlay()
            if self.tray_icon:
                self.tray_icon.show_error(f"Transcription failed: {error_msg}")
                self.tray_icon.set_idle_state()
        finally:
            # Always ensure cleanup happens even if there's an exception
            self.logger.info("Transcription error handler finished, cleanup will occur via signal")

    def _quit_transcription_thread(self, _result=None):
        """Quit and clean up the transcription thread immediately.

        Called via QueuedConnection so it runs on the main thread after
        the completion/error handlers finish. No timer delay — doing
        cleanup inline prevents a race where a delayed timer destroys
        a newly started thread.
        """
        self.logger.info("Cleaning up transcription thread")
        if self.transcription_thread:
            self.transcription_thread.quit()
            self.transcription_thread.wait(2000)
            self.transcription_thread.deleteLater()
            self.transcription_thread = None
        if self.transcription_worker:
            self.transcription_worker.deleteLater()
            self.transcription_worker = None
        self.logger.info("Transcription thread cleanup complete")

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

            self.logger.info("Showing settings dialog as modal")
            # Use exec() to show as modal dialog - this FORCES it to appear
            dialog.exec()

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

        # Update model — defer loading to next transcription to avoid
        # blocking the UI thread on large models.
        model_size = self.config.get_model_size()
        if model_size != self.transcriber.model_size:
            self.logger.info(f"Model changed to '{model_size}', will load on next transcription")
            with self.transcriber._lock:
                self.transcriber.model_size = model_size
                self.transcriber.model = None  # Force reload on next use

        # Update typing speed and method
        self.keyboard_typer.set_typing_speed(self.config.get_typing_speed())
        use_clipboard = self.config.get("typing", "use_clipboard_fallback", default=False)
        self.keyboard_typer.use_clipboard = use_clipboard

        # Update post-processing
        pp_enabled = self.config.get_post_processing_enabled()
        if pp_enabled and self.post_processor is None:
            self.post_processor = PostProcessor()
        elif not pp_enabled and self.post_processor is not None:
            self.post_processor.shutdown()
            self.post_processor = None

        # Update screen context (OCR) — requires post-processing
        ocr_enabled = self.config.get_ocr_enabled() and self.post_processor is not None
        if ocr_enabled and self.screen_context is None:
            self.screen_context = ScreenContextEngine()
        elif not ocr_enabled:
            self.screen_context = None

        # Update overlay feature badges
        self._update_overlay_features()

    def _update_overlay_features(self):
        """Update the recording overlay's feature badges based on config."""
        if not self.overlay:
            return
        features = []
        if self.screen_context is not None:
            features.append("OSR: ON")
        if self.config.get_post_processing_enabled():
            features.append("Post-Processing: ON")
        self.overlay.set_features(features)

    def quit(self):
        """Quit application."""
        self.logger.info("Shutting down...")

        # Unregister hotkey
        self.hotkey_manager.unregister_hotkey()

        # Stop recording if active
        if self.audio_recorder.is_recording():
            self.audio_recorder.stop_recording()

        # Shut down post-processor
        if self.post_processor:
            self.post_processor.shutdown()

        # Quit application
        QApplication.quit()


def main():
    """Main entry point."""
    # Set Windows app ID before creating QApplication
    set_windows_app_id()

    app = QApplication(sys.argv)
    app.setApplicationName("Resonance")
    app.setApplicationDisplayName("Resonance")
    app.setQuitOnLastWindowClosed(False)  # Keep running with system tray

    # Apply dark theme
    apply_theme(app)

    # Create application controller
    vtt_app = VTTApplication()

    # Create recording overlay
    overlay = RecordingOverlay()
    overlay.set_audio_recorder(vtt_app.audio_recorder)
    vtt_app.overlay = overlay
    vtt_app._update_overlay_features()

    # Create clipboard toast indicator
    vtt_app.clipboard_toast = ClipboardToast()

    # Create and setup system tray with formatted hotkey
    tray_icon = SystemTrayIcon(hotkey_display=vtt_app.config.get_hotkey_display())
    vtt_app.tray_icon = tray_icon

    # Connect tray signals
    tray_icon.settings_requested.connect(vtt_app.show_settings)
    tray_icon.quit_requested.connect(vtt_app.quit)

    # Check if model needs downloading
    model_names = {"tiny": "Fastest", "base": "Balanced", "small": "Accurate", "medium": "Precision"}
    model_id = vtt_app.config.get_model_size()
    model_label = model_names.get(model_id, model_id)

    if not vtt_app.transcriber.is_model_downloaded(model_id):
        # Unregister hotkey until model is ready
        vtt_app.hotkey_manager.unregister_hotkey()

        # Show download toast with marquee progress
        download_toast = DownloadToast()
        download_toast.show_download(f"Installing {model_label} model, please wait...")

        # Load model in background thread
        load_thread = QThread()
        load_worker = ModelLoadWorker(vtt_app.transcriber)
        load_worker.moveToThread(load_thread)
        load_thread.started.connect(load_worker.run)

        def _show_post_download_toast():
            """Show startup toast after model download completes."""
            pp_status = "On" if vtt_app.config.get_post_processing_enabled() else "Off"
            ocr_status = "On" if vtt_app.screen_context is not None else "Off"
            use_clipboard = vtt_app.config.get("typing", "use_clipboard_fallback", default=False)
            entry_method = "Clipboard" if use_clipboard else "Character-by-character"

            startup_msg = (
                f"Model downloaded, ready to use\n"
                f"Press {vtt_app.config.get_hotkey_display()} to dictate"
            )
            startup_details = (
                f"Model: {model_label}\n"
                f"OSR: {ocr_status}\n"
                f"Post-processing: {pp_status}\n"
                f"Entry: {entry_method}"
            )
            tray_icon.show_message("Service Started", startup_msg, details=startup_details)

        def on_model_loaded():
            download_toast._anim_timer.stop()
            download_toast._hold_timer.stop()
            download_toast.hide()
            vtt_app.setup_hotkey()
            load_thread.quit()
            # Delay so the event loop processes the hide before showing the new toast
            QTimer.singleShot(500, _show_post_download_toast)

        def on_model_error(msg):
            download_toast._anim_timer.stop()
            download_toast._hold_timer.stop()
            download_toast._message = f"Download failed: {msg}"
            download_toast.update()
            load_thread.quit()
            QTimer.singleShot(3000, download_toast.hide)

        load_worker.finished.connect(on_model_loaded)
        load_worker.error.connect(on_model_error)

        # Keep references alive (prevent GC)
        vtt_app._load_thread = load_thread
        vtt_app._load_worker = load_worker
        vtt_app._download_toast = download_toast

        load_thread.start()
    else:
        # Normal startup — show info toast
        pp_status = "On" if vtt_app.config.get_post_processing_enabled() else "Off"
        ocr_status = "On" if vtt_app.screen_context is not None else "Off"
        use_clipboard = vtt_app.config.get("typing", "use_clipboard_fallback", default=False)
        entry_method = "Clipboard" if use_clipboard else "Character-by-character"

        startup_msg = f"Press {vtt_app.config.get_hotkey_display()} to dictate"
        startup_details = (
            f"Model: {model_label}\n"
            f"OSR: {ocr_status}\n"
            f"Post-processing: {pp_status}\n"
            f"Entry: {entry_method}"
        )
        tray_icon.show_message("Service Started", startup_msg, details=startup_details)

    # Run application
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
