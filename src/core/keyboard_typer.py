"""
Keyboard typing simulation module using pynput.
Types text into the currently focused window.
"""

from pynput.keyboard import Controller, Key
import time
import pyperclip


class KeyboardTyper:
    """Simulates keyboard input to type text into active window."""

    def __init__(self, typing_speed=0.01, use_clipboard=False):
        """
        Initialize keyboard typer.

        Args:
            typing_speed: Delay in seconds between each character (default 0.01 = 10ms)
            use_clipboard: If True, use clipboard+paste instead of typing
        """
        self.controller = Controller()
        self.typing_speed = typing_speed
        self.use_clipboard = use_clipboard

    def set_typing_speed(self, speed):
        """
        Set typing speed.

        Args:
            speed: Delay in seconds between characters (0 for instant)
        """
        self.typing_speed = max(0, speed)

    def type_text(self, text):
        """
        Type text into the currently focused window.
        Uses clipboard method if use_clipboard is True.

        Args:
            text: String to type

        Returns:
            True if successful, False otherwise
        """
        if not text:
            return False

        # Use clipboard method if enabled
        if self.use_clipboard:
            return self.paste_from_clipboard(text)

        try:
            # Small initial delay to ensure window is ready
            time.sleep(0.1)

            # Type each character with delay
            for char in text:
                self.controller.type(char)
                if self.typing_speed > 0:
                    time.sleep(self.typing_speed)

            return True

        except Exception as e:
            print(f"Typing error: {e}")
            # Fallback to clipboard on error
            return self.paste_from_clipboard(text)

    def paste_from_clipboard(self, text):
        """
        Copy text to clipboard and paste it using Ctrl+V.
        More reliable than typing for long text.

        Args:
            text: String to paste

        Returns:
            True if successful, False otherwise
        """
        try:
            # Copy text to clipboard
            pyperclip.copy(text)

            # Small delay
            time.sleep(0.1)

            # Paste using Ctrl+V
            with self.controller.pressed(Key.ctrl):
                self.controller.press('v')
                self.controller.release('v')

            return True

        except Exception as e:
            print(f"Paste error: {e}")
            return False

    def type_text_fast(self, text):
        """
        Type text without delays (faster but potentially less reliable).

        Args:
            text: String to type

        Returns:
            True if successful, False otherwise
        """
        if not text:
            return False

        try:
            # Small initial delay
            time.sleep(0.1)

            # Type entire string at once
            self.controller.type(text)

            return True

        except Exception as e:
            print(f"Fast typing error: {e}")
            return False
