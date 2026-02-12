"""
Configuration management for Will's VTT.
Handles loading, saving, and validating user settings.
"""

import json
import os
from pathlib import Path

from utils.resource_path import get_resource_path, get_app_data_path, is_bundled


def format_hotkey_display(hotkey):
    """
    Format hotkey string for display with proper capitalization.

    Args:
        hotkey: Hotkey string in lowercase format (e.g., 'ctrl+alt+r')

    Returns:
        Formatted hotkey string (e.g., 'Ctrl+Alt+R')
    """
    if not hotkey:
        return ""

    # Split by + and capitalize each part
    parts = hotkey.split('+')
    formatted_parts = []

    for part in parts:
        part = part.strip().lower()
        # Capitalize modifier keys properly
        if part == 'ctrl':
            formatted_parts.append('Ctrl')
        elif part == 'alt':
            formatted_parts.append('Alt')
        elif part == 'shift':
            formatted_parts.append('Shift')
        elif part == 'win':
            formatted_parts.append('Win')
        else:
            # Regular keys - uppercase
            formatted_parts.append(part.upper())

    return '+'.join(formatted_parts)


class ConfigManager:
    """Manages application configuration and settings."""

    DEFAULT_CONFIG = {
        "version": "1.1.0",
        "hotkey": {
            "combination": "ctrl+alt+r",
            "enabled": True
        },
        "whisper": {
            "model_size": "base",
            "language": "en",
            "device": "cpu",
            "compute_type": "int8"
        },
        "audio": {
            "sample_rate": 16000,
            "device_index": None,
            "channels": 1
        },
        "typing": {
            "speed": 0.01,
            "use_clipboard_fallback": True
        },
        "ui": {
            "show_notifications": True,
            "minimize_to_tray": True
        },
        "dictionary": {
            "enabled": True,
            "replacements": {}
        }
    }

    def __init__(self, config_file=None):
        """
        Initialize configuration manager.

        Args:
            config_file: Path to config file (default: ~/.resonance/settings.json)
        """
        if config_file is None:
            # User config file in app data directory (writable location)
            self.config_file = Path(get_app_data_path()) / "settings.json"
        else:
            self.config_file = Path(config_file)

        self.config = self.DEFAULT_CONFIG.copy()
        self.load()

    def load(self):
        """Load configuration from file."""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r') as f:
                    loaded_config = json.load(f)

                # Merge with defaults (in case new settings were added)
                self.config = self._merge_configs(self.DEFAULT_CONFIG, loaded_config)
                print(f"Configuration loaded from {self.config_file}")
            else:
                print(f"No config file found, using defaults")
                self.config = self.DEFAULT_CONFIG.copy()
        except Exception as e:
            print(f"Error loading config: {e}, using defaults")
            self.config = self.DEFAULT_CONFIG.copy()

    def save(self):
        """Save configuration to file."""
        try:
            # Ensure directory exists
            self.config_file.parent.mkdir(parents=True, exist_ok=True)

            # Write config to file
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)

            print(f"Configuration saved to {self.config_file}")
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False

    def get(self, *keys, default=None):
        """
        Get a configuration value using dot notation.

        Args:
            *keys: Path to config value (e.g., "whisper", "model_size")
            default: Default value if key doesn't exist

        Returns:
            Configuration value or default

        Example:
            config.get("whisper", "model_size")  # Returns "small"
        """
        value = self.config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value

    def set(self, *keys, value):
        """
        Set a configuration value using path.

        Args:
            *keys: Path to config value
            value: Value to set

        Example:
            config.set("whisper", "model_size", value="medium")
        """
        if not keys:
            return

        # Navigate to parent dict
        current = self.config
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]

        # Set the value
        current[keys[-1]] = value

    def get_hotkey(self):
        """Get hotkey combination string (lowercase format for internal use)."""
        return self.get("hotkey", "combination", default="ctrl+alt+r")

    def get_hotkey_display(self):
        """Get hotkey combination formatted for display (e.g., 'Ctrl+Alt+R')."""
        hotkey = self.get_hotkey()
        return format_hotkey_display(hotkey)

    def set_hotkey(self, combination):
        """Set hotkey combination."""
        self.set("hotkey", "combination", value=combination)

    def get_model_size(self):
        """Get Whisper model size."""
        return self.get("whisper", "model_size", default="base")

    def set_model_size(self, size):
        """Set Whisper model size."""
        self.set("whisper", "model_size", value=size)

    def get_audio_device(self):
        """Get audio device index."""
        return self.get("audio", "device_index", default=None)

    def set_audio_device(self, device_index):
        """Set audio device index."""
        self.set("audio", "device_index", value=device_index)

    def get_typing_speed(self):
        """Get typing speed (delay between characters)."""
        return self.get("typing", "speed", default=0.01)

    def set_typing_speed(self, speed):
        """Set typing speed."""
        self.set("typing", "speed", value=speed)

    def get_show_notifications(self):
        """Get whether to show notifications."""
        return self.get("ui", "show_notifications", default=True)

    def set_show_notifications(self, show):
        """Set whether to show notifications."""
        self.set("ui", "show_notifications", value=show)

    def _merge_configs(self, default, loaded):
        """
        Merge loaded config with defaults (deep merge).

        Args:
            default: Default configuration dict
            loaded: Loaded configuration dict

        Returns:
            Merged configuration dict
        """
        merged = default.copy()

        for key, value in loaded.items():
            if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                merged[key] = self._merge_configs(merged[key], value)
            else:
                merged[key] = value

        return merged

    def get_dictionary_enabled(self):
        """Get whether custom dictionary is enabled."""
        return self.get("dictionary", "enabled", default=True)

    def set_dictionary_enabled(self, enabled):
        """Set whether custom dictionary is enabled."""
        self.set("dictionary", "enabled", value=enabled)

    def get_dictionary_replacements(self):
        """Get dictionary replacements mapping (wrong word -> correct word)."""
        return self.get("dictionary", "replacements", default={})

    def set_dictionary_replacements(self, replacements):
        """Set dictionary replacements mapping."""
        self.set("dictionary", "replacements", value=replacements)

    def reset_to_defaults(self):
        """Reset configuration to defaults."""
        self.config = self.DEFAULT_CONFIG.copy()
        self.save()
