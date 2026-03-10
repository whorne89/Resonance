"""
Media playback control for Resonance.
Pauses/resumes media during recording using system media keys.
"""

import sys


def _send_media_play_pause():
    """Send the media play/pause key using the platform-native API."""
    if sys.platform == "win32":
        import ctypes
        VK_MEDIA_PLAY_PAUSE = 0xB3
        KEYEVENTF_EXTENDEDKEY = 0x0001
        KEYEVENTF_KEYUP = 0x0002
        ctypes.windll.user32.keybd_event(VK_MEDIA_PLAY_PAUSE, 0, KEYEVENTF_EXTENDEDKEY, 0)
        ctypes.windll.user32.keybd_event(VK_MEDIA_PLAY_PAUSE, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)
    else:
        from pynput.keyboard import Controller, Key
        Controller().tap(Key.media_play_pause)


class MediaController:
    """Sends media play/pause key to pause and resume background media."""

    def __init__(self):
        self._did_pause = False

    def pause_if_playing(self):
        """Send media play/pause key to pause any playing media."""
        try:
            _send_media_play_pause()
            self._did_pause = True
        except Exception:
            self._did_pause = False

    def resume_if_paused(self):
        """Send media play/pause key only if we previously paused."""
        if not self._did_pause:
            return
        try:
            _send_media_play_pause()
        except Exception:
            pass
        finally:
            self._did_pause = False

    def cancel(self):
        """Reset state without sending any key."""
        self._did_pause = False
