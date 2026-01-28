"""
Keyboard typing simulation module using pynput.
Types text into the currently focused window.
"""

from pynput.keyboard import Controller, Key
import time
import pyperclip

from utils.logger import get_logger


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
        self.logger = get_logger()

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
            self.logger.warning("type_text called with empty text")
            return False

        self.logger.info(f"type_text called with {len(text)} chars, use_clipboard={self.use_clipboard}")

        # Use clipboard method if enabled
        if self.use_clipboard:
            return self.paste_from_clipboard(text)

        try:
            # Small initial delay to ensure window is ready
            time.sleep(0.1)

            self.logger.info("Starting character-by-character typing...")
            # Type each character with delay
            for char in text:
                self.controller.type(char)
                if self.typing_speed > 0:
                    time.sleep(self.typing_speed)

            self.logger.info("Character typing completed successfully")
            return True

        except Exception as e:
            self.logger.error(f"Typing error: {e}", exc_info=True)
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
        self.logger.info(f"paste_from_clipboard called with {len(text)} chars")
        try:
            # Copy text to clipboard
            self.logger.info("Copying text to clipboard...")
            pyperclip.copy(text)
            self.logger.info("Text copied to clipboard successfully")

            # Small delay
            time.sleep(0.1)

            # Paste using Ctrl+V
            self.logger.info("Simulating Ctrl+V paste...")
            with self.controller.pressed(Key.ctrl):
                self.controller.press('v')
                self.controller.release('v')

            self.logger.info("Paste simulation completed")
            return True

        except Exception as e:
            self.logger.error(f"Paste error: {e}", exc_info=True)
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
            self.logger.error(f"Fast typing error: {e}", exc_info=True)
            return False
