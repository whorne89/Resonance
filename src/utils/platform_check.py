"""
Platform-specific checks for Resonance.
Handles macOS Accessibility permission verification.
"""

import sys
import subprocess


def check_accessibility_permission():
    """
    Check if Accessibility access is granted.

    On macOS, returns True if the process has Accessibility permission
    (required for global hotkeys and simulated typing via pynput).
    On other platforms, always returns True.
    """
    if sys.platform != "darwin":
        return True

    try:
        import ctypes
        import ctypes.util

        path = ctypes.util.find_library("ApplicationServices")
        if not path:
            return True  # Can't check, assume OK

        appservices = ctypes.cdll.LoadLibrary(path)
        return bool(appservices.AXIsProcessTrusted())
    except Exception:
        return True  # Can't check, assume OK


def open_accessibility_settings():
    """Open macOS System Settings > Privacy & Security > Accessibility."""
    if sys.platform != "darwin":
        return

    try:
        subprocess.Popen([
            "open",
            "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
        ])
    except Exception:
        pass
