"""
Keyboard typing simulation module using pynput.
Types text into the currently focused window.
"""

import sys
import time

from pynput.keyboard import Controller, Key
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
        self.on_tick = None  # Optional callback called during char-by-char typing
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
            for i, char in enumerate(text):
                self.controller.type(char)
                if self.typing_speed > 0:
                    time.sleep(self.typing_speed)
                if self.on_tick and i % 5 == 0:
                    self.on_tick()

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
        self.logger.info(f"Pasting {len(text)} chars via clipboard")
        try:
            pyperclip.copy(text)

            # Small delay
            time.sleep(0.1)

            # Paste using Ctrl+V (Cmd+V on macOS)
            paste_mod = Key.cmd if sys.platform == "darwin" else Key.ctrl
            with self.controller.pressed(paste_mod):
                self.controller.press('v')
                self.controller.release('v')

            self.logger.info("Paste completed")
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
