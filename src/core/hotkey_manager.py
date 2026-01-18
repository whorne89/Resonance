"""
Global hotkey management using pynput.
Handles system-wide hotkey detection with press/release events.
"""

from pynput import keyboard
import threading


class HotkeyManager:
    """Manages global hotkey listening with separate press/release callbacks."""

    def __init__(self):
        """Initialize hotkey manager."""
        self.listener = None
        self.hotkey_combo = None
        self.is_pressed = False
        self.on_press_callback = None
        self.on_release_callback = None
        self._lock = threading.Lock()
        self.current_keys = set()

    def parse_hotkey_string(self, hotkey_string):
        """
        Parse hotkey string into set of keys.

        Args:
            hotkey_string: String like "ctrl+alt+r" or "ctrl+shift+v"

        Returns:
            Set of keyboard.Key or keyboard.KeyCode objects
        """
        keys = set()
        parts = hotkey_string.lower().split('+')

        for part in parts:
            part = part.strip()

            # Map common modifier names
            if part in ['ctrl', 'control']:
                keys.add(keyboard.Key.ctrl_l)
                keys.add(keyboard.Key.ctrl_r)
            elif part in ['alt']:
                keys.add(keyboard.Key.alt_l)
                keys.add(keyboard.Key.alt_r)
            elif part in ['shift']:
                keys.add(keyboard.Key.shift_l)
                keys.add(keyboard.Key.shift_r)
            elif part in ['win', 'windows', 'cmd', 'super']:
                keys.add(keyboard.Key.cmd_l)
                keys.add(keyboard.Key.cmd_r)
            else:
                # Regular character key
                try:
                    keys.add(keyboard.KeyCode.from_char(part))
                except:
                    print(f"Warning: Unknown key '{part}' in hotkey string")

        return keys

    def is_hotkey_pressed(self, hotkey_set):
        """
        Check if the hotkey combination is currently pressed.

        Args:
            hotkey_set: Set of keys that make up the hotkey

        Returns:
            True if all keys in hotkey are pressed
        """
        # For each key in hotkey, check if at least one variant is pressed
        for required_key in hotkey_set:
            # Handle modifier keys (both left and right variants)
            if required_key in [keyboard.Key.ctrl_l, keyboard.Key.ctrl_r]:
                if not (keyboard.Key.ctrl_l in self.current_keys or
                       keyboard.Key.ctrl_r in self.current_keys):
                    return False
            elif required_key in [keyboard.Key.alt_l, keyboard.Key.alt_r]:
                if not (keyboard.Key.alt_l in self.current_keys or
                       keyboard.Key.alt_r in self.current_keys):
                    return False
            elif required_key in [keyboard.Key.shift_l, keyboard.Key.shift_r]:
                if not (keyboard.Key.shift_l in self.current_keys or
                       keyboard.Key.shift_r in self.current_keys):
                    return False
            elif required_key in [keyboard.Key.cmd_l, keyboard.Key.cmd_r]:
                if not (keyboard.Key.cmd_l in self.current_keys or
                       keyboard.Key.cmd_r in self.current_keys):
                    return False
            else:
                # Regular key
                if required_key not in self.current_keys:
                    return False

        return True

    def register_hotkey(self, hotkey_string, on_press, on_release):
        """
        Register a global hotkey with press and release callbacks.

        Args:
            hotkey_string: String like "ctrl+alt+r"
            on_press: Function to call when hotkey is pressed
            on_release: Function to call when hotkey is released
        """
        # Stop existing listener
        self.unregister_hotkey()

        # Parse hotkey string
        self.hotkey_combo = self.parse_hotkey_string(hotkey_string)
        if not self.hotkey_combo:
            raise ValueError(f"Invalid hotkey string: {hotkey_string}")

        self.on_press_callback = on_press
        self.on_release_callback = on_release
        self.is_pressed = False

        def on_key_press(key):
            """Handle key press events."""
            try:
                with self._lock:
                    self.current_keys.add(key)

                    # Check if hotkey combo is now pressed
                    if not self.is_pressed and self.is_hotkey_pressed(self.hotkey_combo):
                        self.is_pressed = True
                        if self.on_press_callback:
                            # Run callback in separate thread to avoid blocking
                            threading.Thread(
                                target=self.on_press_callback,
                                daemon=True
                            ).start()
            except Exception as e:
                print(f"Error in on_key_press: {e}")

        def on_key_release(key):
            """Handle key release events."""
            try:
                with self._lock:
                    # Remove key from current set
                    if key in self.current_keys:
                        self.current_keys.remove(key)

                    # Check if hotkey combo is now released
                    if self.is_pressed and not self.is_hotkey_pressed(self.hotkey_combo):
                        self.is_pressed = False
                        if self.on_release_callback:
                            # Run callback in separate thread
                            threading.Thread(
                                target=self.on_release_callback,
                                daemon=True
                            ).start()
            except Exception as e:
                print(f"Error in on_key_release: {e}")

        # Start keyboard listener
        self.listener = keyboard.Listener(
            on_press=on_key_press,
            on_release=on_key_release
        )
        self.listener.start()

        print(f"Registered global hotkey: {hotkey_string}")

    def unregister_hotkey(self):
        """Stop listening for hotkeys."""
        if self.listener:
            self.listener.stop()
            self.listener = None
        self.current_keys.clear()
        self.is_pressed = False
        self.hotkey_combo = None

    def is_listening(self):
        """Check if currently listening for hotkeys."""
        return self.listener is not None and self.listener.running
