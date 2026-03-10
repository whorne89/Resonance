"""
Media playback control for Resonance.
Pauses/resumes media during recording using system media keys.
"""

from pynput.keyboard import Controller, Key


class MediaController:
    """Sends media play/pause key to pause and resume background media."""

    def __init__(self):
        self._keyboard = Controller()
        self._did_pause = False

    def pause_if_playing(self):
        """Send media play/pause key to pause any playing media."""
        try:
            self._keyboard.tap(Key.media_play_pause)
            self._did_pause = True
        except Exception:
            self._did_pause = False

    def resume_if_paused(self):
        """Send media play/pause key only if we previously paused."""
        if not self._did_pause:
            return
        try:
            self._keyboard.tap(Key.media_play_pause)
        except Exception:
            pass
        finally:
            self._did_pause = False

    def cancel(self):
        """Reset state without sending any key."""
        self._did_pause = False
