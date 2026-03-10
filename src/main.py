"""
Resonance - Voice to Text Application
Main entry point that orchestrates all components.
"""

import os
import sys

# PyInstaller windowed mode (console=False) sets sys.stdout/stderr to None.
# Libraries like huggingface_hub use tqdm which calls sys.stderr.write(),
# crashing with "NoneType has no attribute 'write'". Redirect to devnull.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

import time
import traceback
import threading
from datetime import date
from PySide6.QtWidgets import QApplication, QVBoxLayout, QLabel, QProgressBar, QHBoxLayout, QPushButton
from PySide6.QtCore import QObject, Signal, QThread, QTimer, Qt
from PySide6.QtGui import QIcon

from core.debug_manager import DebugManager
from core.audio_recorder import AudioRecorder
from core.transcriber import Transcriber
from core.keyboard_typer import KeyboardTyper
from core.hotkey_manager import HotkeyManager
from core.dictionary import DictionaryProcessor
from core.learning_engine import KNOWN_APPS, LearningEngine
from core.post_processor import PostProcessor
from core.screen_context import AppType, ScreenContextEngine
from core.media_control import MediaController
from core.sound_effects import SoundEffects
from core.text_cleaners import clean_comma_spam, replace_spoken_punctuation
from gui.recording_overlay import RecordingOverlay
from gui.system_tray import SystemTrayIcon
from gui.settings_dialog import SettingsDialog
from gui.theme import apply_theme
from gui.toast_notification import ClipboardToast, DownloadToast
from utils.config import ConfigManager
from utils.logger import setup_logger
from utils.resource_path import get_resource_path


def set_windows_app_id():
    """Set Windows AppUserModelID for proper taskbar/tray display."""
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        app_id = "Resonance.VoiceToText.1.0"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass  # API not available


class TranscriptionWorker(QObject):
    """Worker for running transcription in background thread."""

    finished = Signal(str, float)  # Emits transcribed text + confidence (0.0-1.0)
    error = Signal(str)  # Emits error message
    debug_info = Signal(dict)  # Emits debug data collected during run

    def __init__(self, transcriber, audio_data, post_processor=None, logger=None,
                 ocr_context=None, learned_vocabulary=None, style_suffix=None,
                 spoken_punctuation=False, debug_enabled=False):
        super().__init__()
        self.transcriber = transcriber
        self.audio_data = audio_data
        self.post_processor = post_processor
        self.logger = logger
        self.ocr_context = ocr_context
        self.learned_vocabulary = learned_vocabulary or []
        self.style_suffix = style_suffix
        self.spoken_punctuation = spoken_punctuation
        self.debug_enabled = debug_enabled
        self._debug_data = {}

    def run(self):
        """Run transcription."""
        try:
            # Build OCR-derived hints if available
            initial_prompt = None
            system_prompt = None
            if self.ocr_context:
                # Merge OCR proper nouns with learned vocabulary from past sessions
                all_nouns = list(self.ocr_context.proper_nouns)
                if self.learned_vocabulary:
                    seen = {n.lower() for n in all_nouns}
                    for term in self.learned_vocabulary:
                        if term.lower() not in seen:
                            all_nouns.append(term)
                            seen.add(term.lower())

                initial_prompt = ScreenContextEngine.build_whisper_prompt(
                    all_nouns, self.ocr_context.app_type
                )
                system_prompt = ScreenContextEngine.build_system_prompt(
                    self.ocr_context.app_type, all_nouns
                )

                # Append learned style hints to system prompt
                if self.style_suffix and system_prompt:
                    system_prompt += f"\n\n{self.style_suffix}"

                if self.logger:
                    self.logger.info(f"OCR context: app_type={self.ocr_context.app_type.value}, "
                                    f"names={self.ocr_context.names}, "
                                    f"words={self.ocr_context.vocabulary}, "
                                    f"learned_vocab={len(self.learned_vocabulary)}")

            if self.logger:
                self.logger.info("Starting transcription...")
            _t0 = time.perf_counter()
            text = self.transcriber.transcribe(self.audio_data, initial_prompt=initial_prompt)
            _whisper_ms = round((time.perf_counter() - _t0) * 1000)
            if self.logger:
                self.logger.info(f"Transcription finished, got {len(text)} characters")

            if self.debug_enabled:
                self._debug_data["whisper_raw"] = text
                self._debug_data["whisper_confidence"] = getattr(self.transcriber, 'last_confidence', 0.0)
                self._debug_data["whisper_model"] = getattr(self.transcriber, 'model_size', '')
                self._debug_data["initial_prompt"] = initial_prompt or ""
                self._debug_data["whisper_ms"] = _whisper_ms

            # Clean comma spam from Whisper output (always on)
            if text:
                original = text
                text = clean_comma_spam(text)
                if text != original and self.logger:
                    self.logger.info(f"Comma spam cleaned: '{original}' -> '{text}'")

            if self.debug_enabled:
                self._debug_data["after_comma_clean"] = text
                self._debug_data["comma_spam_triggered"] = (text != original) if text else False

            # Replace spoken punctuation (e.g., "slash" -> "/")
            # Only in terminal/code contexts where symbols are expected
            if text and self.spoken_punctuation and self.ocr_context:
                if self.ocr_context.app_type in (AppType.CODE, AppType.TERMINAL):
                    original = text
                    text = replace_spoken_punctuation(text)
                    if text != original and self.logger:
                        self.logger.info(f"Spoken punctuation: '{original}' -> '{text}'")

            if self.debug_enabled:
                self._debug_data["spoken_punctuation_applied"] = (
                    text != self._debug_data.get("after_comma_clean", text)
                ) if text else False
                self._debug_data["after_text_cleanup"] = text

            # Guard: detect Whisper hallucinating from initial_prompt
            # Whisper regurgitates OCR nouns as output even from silence/noise.
            # Only discard when EVERY word is an OCR noun (pure regurgitation).
            # Mixed phrases like "Hey Jordan" contain non-noun words, indicating real speech.
            if text and self.ocr_context and self.ocr_context.proper_nouns:
                words = text.replace('.', ' ').replace(',', ' ').split()
                if 0 < len(words) <= 4:
                    nouns_lower = {n.lower() for n in self.ocr_context.proper_nouns}
                    noun_hits = sum(1 for w in words if w.lower() in nouns_lower)
                    if noun_hits == len(words):
                        if self.logger:
                            self.logger.warning(
                                f"Prompt hallucination detected: '{text}' — "
                                f"{noun_hits}/{len(words)} words from OCR nouns, discarding"
                            )
                        text = ""

            if text and self.post_processor:
                original_before_pp = text
                if self.logger:
                    self.logger.info("Running post-processing...")
                _t0 = time.perf_counter()
                text = self.post_processor.process(text, system_prompt=system_prompt)
                _pp_ms = round((time.perf_counter() - _t0) * 1000)
                if self.logger:
                    self.logger.info(f"Post-processing finished, got {len(text)} characters")

                if self.debug_enabled:
                    self._debug_data["pp_input"] = original_before_pp
                    self._debug_data["pp_output"] = text
                    self._debug_data["pp_ms"] = _pp_ms
                    self._debug_data["pp_system_prompt_type"] = (
                        self.ocr_context.app_type.value if self.ocr_context else ""
                    )

            # Apply structural formatting based on app type
            if self.ocr_context and text:
                if self.ocr_context.app_type == AppType.CHAT:
                    text = ScreenContextEngine.apply_chat_formatting(text)

            confidence = getattr(self.transcriber, 'last_confidence', 0.0)
            if self.debug_enabled:
                self.debug_info.emit(self._debug_data)
            self.finished.emit(text, confidence)
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


class _UpdateCheckWorker(QObject):
    """Worker for checking GitHub Releases in a background thread."""

    update_available = Signal(str, str, str, str)  # version, download_url, tag_name, release_body
    up_to_date = Signal()

    def run(self):
        from core.updater import UpdateChecker
        checker = UpdateChecker()
        info = checker.check_for_update()
        if info:
            self.update_available.emit(info.version_str, info.download_url, info.tag_name, info.release_body)
        else:
            self.up_to_date.emit()


class _UpdateDownloadWorker(QObject):
    """Worker for downloading an update in a background thread."""

    finished = Signal(str)  # downloaded file path
    error = Signal(str)
    progress = Signal(int, int)  # downloaded, total

    def __init__(self, version_str, download_url):
        super().__init__()
        self.version_str = version_str
        self.download_url = download_url

    def run(self):
        from core.updater import UpdateChecker, UpdateInfo
        checker = UpdateChecker()
        info = UpdateInfo(
            version_str=self.version_str,
            tag_name="",
            download_url=self.download_url,
        )
        path = checker.download_update(info, progress_callback=self._on_progress)
        if path:
            self.finished.emit(path)
        else:
            self.error.emit("Download failed")

    def _on_progress(self, downloaded, total):
        self.progress.emit(downloaded, total)


class VTTApplication(QObject):
    """Main application controller."""

    # Signals for thread-safe hotkey handling.
    # Hotkey callbacks fire from background threads — these signals
    # marshal execution to the main Qt thread via QueuedConnection.
    _hotkey_pressed = Signal()
    _hotkey_released = Signal()

    # Relay signals for worker threads → main thread marshaling.
    # PySide6 QueuedConnection doesn't work for plain Python functions
    # (no receiver QObject to determine target thread). Chain through
    # these signals instead: worker signal → relay signal → callback.
    _relay_model_loaded = Signal()
    _relay_model_error = Signal(str)
    _relay_update = Signal(str, str, str, str)  # version, url, tag, release_body
    _relay_up_to_date = Signal()
    _relay_dl_progress = Signal(int, int)     # downloaded, total
    _relay_dl_finished = Signal(str)          # path
    _relay_dl_error = Signal(str)

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

        # Self-learning engine — learns from OCR data over time
        self.learning_engine = None
        if self.config.get_learning_enabled() and self.screen_context is not None:
            self.learning_engine = LearningEngine()

        # Media controller — pauses/resumes media during recording
        self.media_controller = None
        if self.config.get_pause_media_enabled():
            self.media_controller = MediaController()

        # Debug manager (created if debug mode enabled)
        self.debug_manager = None
        self.debug_panel = None
        self._init_debug()

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

    def _init_debug(self):
        """Initialize or tear down debug manager based on config."""
        debug_enabled = self.config.get_debug_enabled()

        if debug_enabled:
            if self.debug_manager is None:
                self.debug_manager = DebugManager(
                    logging_enabled=self.config.get_debug_logging_enabled(),
                    live_panel_enabled=self.config.get_debug_live_panel_enabled(),
                )

                # Create live panel if enabled
                if self.config.get_debug_live_panel_enabled():
                    from gui.debug_panel import DebugPanel
                    self.debug_panel = DebugPanel()
                    # Connect signals
                    self.debug_manager.recording_started.connect(self.debug_panel.on_recording_started)
                    self.debug_manager.recording_stopped.connect(self.debug_panel.on_recording_stopped)
                    self.debug_manager.ocr_completed.connect(self.debug_panel.on_ocr_completed)
                    self.debug_manager.transcription_completed.connect(self.debug_panel.on_transcription_completed)
                    self.debug_manager.post_processing_completed.connect(self.debug_panel.on_post_processing_completed)
                    self.debug_manager.text_cleanup_completed.connect(self.debug_panel.on_text_cleanup_completed)
                    self.debug_manager.dictionary_completed.connect(self.debug_panel.on_dictionary_completed)
                    self.debug_manager.learning_completed.connect(self.debug_panel.on_learning_completed)
                    self.debug_manager.session_completed.connect(self.debug_panel.on_session_completed)
            else:
                # Update settings on existing manager
                self.debug_manager.logging_enabled = self.config.get_debug_logging_enabled()
                self.debug_manager.live_panel_enabled = self.config.get_debug_live_panel_enabled()
        else:
            if self.debug_panel:
                self.debug_panel.dismiss()
                self.debug_panel.deleteLater()
                self.debug_panel = None
            self.debug_manager = None

    def on_hotkey_press(self):
        """Called when hotkey is pressed - start recording."""
        try:
            # Guard: ignore if already recording (spurious re-press)
            if self.audio_recorder.is_recording():
                self.logger.warning("Ignoring hotkey press — already recording")
                return

            self.logger.info("Hotkey pressed - starting recording")

            if self.debug_manager:
                self.debug_manager.start_session()

            # Play start tone before recording to avoid capturing it
            self.sound_effects.play_start_tone()

            # Pause background media so it doesn't interfere with voice capture
            if self.media_controller:
                self.media_controller.pause_if_playing()

            self.audio_recorder.start_recording()

            # Fire OCR capture in background (non-blocking, runs during recording)
            if self.screen_context:
                def _capture_ocr():
                    try:
                        self._current_ocr_context = self.screen_context.capture()
                        if self._current_ocr_context and self.debug_manager:
                            ctx = self._current_ocr_context
                            self.debug_manager.record_ocr(
                                ctx.app_type.value, ctx.window_title,
                                ctx.proper_nouns, len(ctx.raw_text),
                                names=ctx.names, vocabulary=ctx.vocabulary,
                            )
                        # Feed learning engine with OCR data
                        if self._current_ocr_context and self.learning_engine:
                            ctx = self._current_ocr_context
                            self.learning_engine.learn_from_context(
                                ctx.window_title, ctx.raw_text, ctx.app_type.value
                            )
                            self.learning_engine.save()
                    except Exception as e:
                        self.logger.warning(f"OCR capture failed: {e}")
                        self._current_ocr_context = None
                threading.Thread(target=_capture_ocr, daemon=True).start()
            else:
                self._current_ocr_context = None
                if self.debug_panel:
                    self.debug_panel.on_ocr_skipped()

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
                if self.media_controller:
                    self.media_controller.resume_if_paused()
                if self.tray_icon:
                    self.tray_icon.set_idle_state()
                if self.overlay:
                    self.overlay.hide_overlay()
                return

            self.logger.info(f"Audio recorded: {len(audio_data)} samples")
            self._last_audio_samples = len(audio_data)

            if self.debug_manager:
                duration = len(audio_data) / self.audio_recorder.sample_rate
                self.debug_manager.record_audio(
                    duration, self.audio_recorder.current_rms,
                    self.audio_recorder.sample_rate,
                )

            # Update UI to transcribing state
            if self.tray_icon:
                self.tray_icon.set_transcribing_state()
            if self.overlay:
                self.overlay.show_processing()

            # Run transcription in background thread
            self.start_transcription(audio_data)

        except Exception as e:
            self.logger.error(f"Failed to process recording: {e}")
            if self.media_controller:
                self.media_controller.resume_if_paused()
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

        # Extract learned vocabulary and style hints if learning engine is active
        learned_vocabulary = []
        style_suffix = None
        if self.learning_engine and self._current_ocr_context:
            title = self._current_ocr_context.window_title
            learned_vocabulary = self.learning_engine.get_vocabulary(title)
            app_type_str = self._current_ocr_context.app_type.value if self._current_ocr_context else None
            style_suffix = self.learning_engine.build_style_prompt_suffix(title, app_type=app_type_str)
            if learned_vocabulary:
                self.logger.info(f"Learning: {len(learned_vocabulary)} vocab terms for '{title[:30]}'")
            if style_suffix:
                self.logger.info(f"Learning: style hints: {style_suffix}")

        if self.debug_manager:
            _profile = (
                self.learning_engine.get_profile(self._current_ocr_context.window_title)
                if self.learning_engine and self._current_ocr_context else None
            )
            self.debug_manager.record_learning(
                enabled=self.learning_engine is not None,
                app_key=_profile.app_key if _profile else None,
                vocabulary_injected=learned_vocabulary,
                style_suffix=style_suffix,
                style_metrics=_profile.style_metrics.to_dict() if _profile else None,
                sessions_count=_profile.sessions if _profile else 0,
                confidence=_profile.confidence if _profile else 0.0,
            )

        # Create worker and thread
        self.transcription_thread = QThread()
        self.transcription_worker = TranscriptionWorker(
            self.transcriber, audio_data, self.post_processor, self.logger,
            ocr_context=self._current_ocr_context,
            learned_vocabulary=learned_vocabulary,
            style_suffix=style_suffix,
            spoken_punctuation=self.config.get_spoken_punctuation_enabled(),
            debug_enabled=self.debug_manager is not None,
        )

        # Move worker to thread
        self.transcription_worker.moveToThread(self.transcription_thread)

        # Connect signals
        self.transcription_thread.started.connect(self.transcription_worker.run)
        self.transcription_worker.finished.connect(self.on_transcription_complete)
        self.transcription_worker.error.connect(self.on_transcription_error)
        if self.debug_manager:
            self.transcription_worker.debug_info.connect(self._on_debug_info)

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

    def _on_debug_info(self, data):
        """Process debug data from transcription worker."""
        if not self.debug_manager:
            return

        # Record transcription (timing captured inside worker thread)
        self.debug_manager.record_transcription(
            model=data.get("whisper_model", ""),
            raw_output=data.get("whisper_raw", ""),
            confidence=data.get("whisper_confidence", 0.0),
            initial_prompt=data.get("initial_prompt", ""),
            timing_ms=data.get("whisper_ms", 0),
        )

        # Record text cleanup
        self.debug_manager.record_text_cleanup(
            input_text=data.get("whisper_raw", ""),
            output_text=data.get("after_text_cleanup", ""),
            comma_spam_triggered=data.get("comma_spam_triggered", False),
            spoken_punctuation_applied=data.get("spoken_punctuation_applied", False),
        )

        # Record post-processing (timing captured inside worker thread)
        if data.get("pp_output") is not None:
            self.debug_manager.record_post_processing(
                input_text=data.get("pp_input", ""),
                output_text=data.get("pp_output", ""),
                system_prompt_type=data.get("pp_system_prompt_type", ""),
                timing_ms=data.get("pp_ms", 0),
            )
        elif self.debug_panel:
            self.debug_panel.on_post_processing_skipped()

    def on_transcription_complete(self, text, confidence=0.0):
        """
        Called when transcription is complete.

        Args:
            text: Transcribed text
            confidence: Whisper confidence score (0.0-1.0)
        """
        self.logger.info(f"Transcription complete: '{text}' (confidence={confidence:.0%})")

        # If a new recording is already in progress, this is a stale
        # completion from a previous session.  Process text normally but
        # do NOT touch the overlay or tray — they belong to the new session.
        new_recording_active = self.audio_recorder.is_recording()
        if new_recording_active:
            self.logger.warning("Stale transcription completed while recording — suppressing UI updates")

        try:
            # Apply custom dictionary replacements
            original = text
            if text:
                text = self.dictionary.apply(text)
                if text != original:
                    self.logger.info(f"Dictionary applied: '{original}' -> '{text}'")

            if self.debug_manager:
                self.debug_manager.record_dictionary(
                    replacements_applied={} if not original or text == original else {"original": original, "replaced": text},
                    output_text=text or "",
                )

            # Update usage statistics
            if text:
                self._update_statistics(text)

            # Type the text
            if text:
                try:
                    self.logger.info("Starting text output...")
                    if not new_recording_active:
                        # Set accuracy and detected app for overlay badges
                        if self.overlay:
                            self.overlay.set_accuracy(confidence)
                            if self.learning_engine is not None:
                                # Self-learning: show specific app (e.g., "Discord")
                                self.overlay.set_detected_app(
                                    self._resolve_app_label(self._current_ocr_context)
                                )
                            elif self.screen_context is not None:
                                # OSR only: show generic type (e.g., "Chat")
                                self.overlay.set_detected_app(
                                    self._resolve_type_label(self._current_ocr_context)
                                )
                            else:
                                self.overlay.set_detected_app(None)
                        # Show typing state on overlay for char-by-char mode
                        if not self.keyboard_typer.use_clipboard and self.overlay:
                            self.overlay.show_typing()
                            QApplication.processEvents()  # Repaint before blocking type loop
                    # Run typing with error handling
                    success = self.keyboard_typer.type_text(text)
                    if success:
                        self.logger.info("Text output successful")
                        if not new_recording_active:
                            # Show green completion state on overlay
                            if self.overlay:
                                if self.keyboard_typer.use_clipboard:
                                    self.overlay.show_pasted()
                                else:
                                    self.overlay.show_complete()
                                QApplication.processEvents()
                    else:
                        self.logger.warning("Text output failed")

                    if self.debug_manager:
                        method = "clipboard" if self.keyboard_typer.use_clipboard else "typing"
                        self.debug_manager.record_delivery(method, len(text))
                        self.debug_manager.finish_session(text)
                except Exception as e:
                    self.logger.error(f"Error outputting text: {e}")
                    if self.tray_icon and not new_recording_active:
                        self.tray_icon.show_error(f"Failed to paste text: {e}")
            else:
                self.logger.warning("Transcription returned empty text")
                if not new_recording_active and self.overlay:
                    self.overlay.show_no_speech()
                if self.debug_manager:
                    self.debug_manager.finish_session("")

            # Reset UI — only if no new recording has started
            if not new_recording_active:
                if self.tray_icon:
                    self.tray_icon.set_idle_state()
                if self.overlay:
                    # Brief hold before fading out
                    self.overlay.hide_overlay(delay_ms=600)
        finally:
            # Resume media only if no new recording started (would re-pause anyway)
            if self.media_controller and not new_recording_active:
                self.media_controller.resume_if_paused()
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
            if self.media_controller:
                self.media_controller.resume_if_paused()
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

        # Update learning engine — requires screen context
        learning_enabled = self.config.get_learning_enabled() and self.screen_context is not None
        if learning_enabled and self.learning_engine is None:
            self.learning_engine = LearningEngine()
        elif not learning_enabled:
            if self.learning_engine:
                self.learning_engine.save()
            self.learning_engine = None

        # Update media controller
        pause_media = self.config.get_pause_media_enabled()
        if pause_media and self.media_controller is None:
            self.media_controller = MediaController()
        elif not pause_media and self.media_controller is not None:
            self.media_controller.cancel()
            self.media_controller = None

        # Refresh debug manager
        self._init_debug()

        # Update overlay feature badges
        self._update_overlay_features()

    def _resolve_type_label(self, ocr_context):
        """Resolve a generic type label from OCR context (e.g., "Chat", "Email").

        Used when OSR is on but self-learning is off.
        Returns None for "general" type.
        """
        if not ocr_context:
            return None
        app_type = ocr_context.app_type.value
        if app_type == "general":
            return None
        return app_type.capitalize()

    def _resolve_app_label(self, ocr_context):
        """Resolve a display label for the detected app.

        Returns specific app name (e.g. "Discord") if recognized,
        otherwise the generic type (e.g. "Chat", "General").
        """
        if not ocr_context:
            return None
        # Try to match window title against known apps for a specific name
        title_lower = ocr_context.window_title.lower() if ocr_context.window_title else ""
        for app_name in sorted(KNOWN_APPS, key=len, reverse=True):
            if app_name in title_lower:
                _, display_name, _ = KNOWN_APPS[app_name]
                return display_name
        # Fall back to generic type
        app_type = ocr_context.app_type.value
        if app_type == "general":
            return None
        return app_type.capitalize()

    def _update_overlay_features(self):
        """Update the recording overlay's feature badges based on config."""
        if not self.overlay:
            return
        features = []
        if self.learning_engine is not None:
            features.append("Learning OSR")
        elif self.screen_context is not None:
            features.append("Post-Processing OSR")
        elif self.post_processor is not None:
            features.append("Post-Processing")
        self.overlay.set_features(features)

    def quit(self):
        """Quit application."""
        self.logger.info("Shutting down...")

        # Unregister hotkey
        self.hotkey_manager.unregister_hotkey()

        # Stop recording if active
        if self.audio_recorder.is_recording():
            self.audio_recorder.stop_recording()

        # Save learning data
        if self.learning_engine:
            self.learning_engine.save()

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

    # Set application icon for taskbar and window title bars
    icon_path = get_resource_path("icons/tray_idle.png")
    if icon_path:
        app.setWindowIcon(QIcon(icon_path))

    # Apply dark theme
    apply_theme(app)

    # Create application controller
    vtt_app = VTTApplication()

    # Global exception hook — catches uncaught exceptions from any thread
    def handle_exception(exctype, value, tb):
        error_msg = f"{exctype.__name__}: {value}\n{''.join(traceback.format_tb(tb))}"
        try:
            vtt_app.logger.error(f"Uncaught exception: {error_msg}")
        except Exception:
            print(f"ERROR: {error_msg}", file=sys.stderr)

    sys.excepthook = handle_exception

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

    def _build_startup_details():
        """Build the startup toast details string."""
        pp_status = "On" if vtt_app.config.get_post_processing_enabled() else "Off"
        if vtt_app.screen_context is not None:
            osr_status = "Learning OSR: On" if vtt_app.config.get_learning_enabled() else "OSR: On"
        else:
            osr_status = "OSR: Off"
        use_clipboard = vtt_app.config.get("typing", "use_clipboard_fallback", default=False)
        entry_method = "Clipboard" if use_clipboard else "Character-by-character"
        details = (
            f"Model: {model_label}\n"
            f"{osr_status}\n"
            f"Post-processing: {pp_status}\n"
            f"Entry: {entry_method}"
        )
        # Show hint on first-ever launch before any transcription has been done
        stats = vtt_app.config.get_statistics()
        if not stats.get("first_used"):
            details += "\n\nFirst use may take longer while the model loads"
        return details

    # Clean up any partial/failed model downloads before checking
    vtt_app.transcriber.clean_partial_download(model_id)

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
            startup_msg = (
                f"Model downloaded, ready to use\n"
                f"Press {vtt_app.config.get_hotkey_display()} to dictate"
            )
            tray_icon.show_message("Service Started", startup_msg, details=_build_startup_details())

        def on_model_loaded():
            download_toast._downloading = False
            download_toast._anim_timer.stop()
            download_toast._hold_timer.stop()
            download_toast._stop_fade()
            download_toast.setWindowOpacity(0.0)
            download_toast.hide()
            vtt_app.setup_hotkey()
            load_thread.quit()
            QTimer.singleShot(300, _show_post_download_toast)

        def on_model_error(msg):
            download_toast._anim_timer.stop()
            download_toast._hold_timer.stop()
            download_toast._message = f"Download failed: {msg}"
            download_toast.update()
            load_thread.quit()
            QTimer.singleShot(3000, download_toast.hide)

        # Relay through vtt_app (QObject on main thread) to guarantee
        # callbacks run on the main thread. Direct QueuedConnection to
        # plain functions doesn't work in PySide6.
        load_worker.finished.connect(vtt_app._relay_model_loaded)
        load_worker.error.connect(vtt_app._relay_model_error)
        vtt_app._relay_model_loaded.connect(on_model_loaded)
        vtt_app._relay_model_error.connect(on_model_error)

        # Keep references alive (prevent GC)
        vtt_app._load_thread = load_thread
        vtt_app._load_worker = load_worker
        vtt_app._download_toast = download_toast

        load_thread.start()
    else:
        # Normal startup — show info toast
        vtt_app.logger.info("Model already downloaded, showing startup toast")
        startup_msg = f"Press {vtt_app.config.get_hotkey_display()} to dictate"
        tray_icon.show_message("Service Started", startup_msg, details=_build_startup_details())
        vtt_app.logger.info("Startup toast shown")

    # --- Auto-update check (8s after launch) ---
    def _start_update_check():
        from gui.update_toast import UpdateToast
        from gui.theme import RoundedDialog

        thread = QThread()
        worker = _UpdateCheckWorker()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)

        def _on_update_available(version_str, download_url, tag_name, release_body):
            try:
                vtt_app.logger.info(f"Update callback: {version_str}, showing toast")
                thread.quit()
                from utils.resource_path import is_bundled

                toast = UpdateToast(version_str)

                def _on_accepted():
                    toast.hide()
                    if is_bundled():
                        from gui.changelog_dialog import ChangelogDialog
                        changelog = ChangelogDialog(version_str, release_body)
                        vtt_app._changelog_dialog = changelog
                        changelog.exec()
                        if changelog.was_accepted():
                            _download_and_apply(version_str, download_url, vtt_app)
                    else:
                        from core.updater import UpdateChecker, UpdateInfo
                        info = UpdateInfo(version_str=version_str, tag_name=tag_name, download_url=download_url)
                        msg = UpdateChecker.get_source_update_message(info)
                        tray_icon.show_message("Update Available", msg)

                toast.accepted.connect(_on_accepted)
                toast.show_toast()

                # Keep references alive
                vtt_app._update_toast = toast
                vtt_app.logger.info("Update toast shown successfully")
            except Exception as e:
                vtt_app.logger.error(f"Failed to show update toast: {e}")

        def _on_up_to_date():
            thread.quit()

        # Relay through vtt_app to run callbacks on the main thread
        worker.update_available.connect(vtt_app._relay_update)
        worker.up_to_date.connect(vtt_app._relay_up_to_date)
        vtt_app._relay_update.connect(_on_update_available)
        vtt_app._relay_up_to_date.connect(_on_up_to_date)

        # Keep references alive
        vtt_app._update_thread = thread
        vtt_app._update_worker = worker

        thread.start()

    def _download_and_apply(version_str, download_url, vtt_app):
        """Show download progress dialog, then apply the update."""
        from gui.theme import RoundedDialog

        dlg = RoundedDialog()
        dlg.setWindowTitle("Updating Resonance")
        dlg.setMinimumWidth(420)

        layout = QVBoxLayout()
        layout.setSpacing(12)
        status = QLabel(f"Downloading Resonance {version_str}...")
        status.setStyleSheet("font-size: 12px;")
        layout.addWidget(status)

        bar = QProgressBar()
        bar.setMinimum(0)
        bar.setMaximum(100)
        bar.setValue(0)
        bar.setTextVisible(True)
        bar.setFormat("%v%")
        bar.setMinimumHeight(28)
        layout.addWidget(bar)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dlg.reject)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        dlg.setLayout(layout)

        dl_thread = QThread()
        dl_worker = _UpdateDownloadWorker(version_str, download_url)
        dl_worker.moveToThread(dl_thread)
        dl_thread.started.connect(dl_worker.run)

        def _on_progress(downloaded, total):
            if total > 0:
                pct = min(99, int(downloaded / total * 100))
                bar.setValue(pct)
                mb_done = downloaded / (1024 * 1024)
                mb_total = total / (1024 * 1024)
                status.setText(f"Downloading Resonance {version_str}... {mb_done:.1f} / {mb_total:.1f} MB")

        def _on_finished(path):
            bar.setValue(100)
            dl_thread.quit()
            dlg.accept()
            # Apply the update
            from core.updater import UpdateChecker
            checker = UpdateChecker()
            if checker.apply_update(path):
                vtt_app.quit()

        def _on_error(msg):
            dl_thread.quit()
            status.setText(f"Download failed: {msg}")

        # Relay through vtt_app to run callbacks on the main thread
        dl_worker.progress.connect(vtt_app._relay_dl_progress)
        dl_worker.finished.connect(vtt_app._relay_dl_finished)
        dl_worker.error.connect(vtt_app._relay_dl_error)
        vtt_app._relay_dl_progress.connect(_on_progress)
        vtt_app._relay_dl_finished.connect(_on_finished)
        vtt_app._relay_dl_error.connect(_on_error)

        # Keep references
        dlg._dl_thread = dl_thread
        dlg._dl_worker = dl_worker

        dl_thread.start()
        dlg.exec()

    QTimer.singleShot(8000, _start_update_check)

    # Run application
    try:
        sys.exit(app.exec())
    except Exception as e:
        try:
            vtt_app.logger.error(f"Uncaught exception in app.exec(): {e}")
            vtt_app.logger.error(traceback.format_exc())
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
