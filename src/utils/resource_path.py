"""
Resource path utilities for Resonance.
Handles path resolution for both development and PyInstaller bundled EXE.
"""

import os
import sys
from pathlib import Path


def get_resource_path(relative_path=""):
    """
    Get absolute path to a resource, works for dev and PyInstaller bundle.

    When running as a bundled EXE, resources are extracted to sys._MEIPASS.
    When running as a script, resources are relative to the src directory.

    Args:
        relative_path: Path relative to resources directory (e.g., "icons/tray_idle.png")

    Returns:
        Absolute path to the resource
    """
    if hasattr(sys, '_MEIPASS'):
        # Running as bundled exe - resources are in _MEIPASS/resources/
        base_path = os.path.join(sys._MEIPASS, 'resources')
    else:
        # Running as script - resources are in src/resources/
        base_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'resources')

    if relative_path:
        return os.path.join(base_path, relative_path)
    return base_path


def get_app_data_path(subdir=""):
    """
    Get path to application data directory (for user-writable data like models).

    Uses ~/.resonance/ on all platforms for persistent storage.

    Args:
        subdir: Subdirectory within app data (e.g., "models", "cache")

    Returns:
        Absolute path to the app data directory
    """
    app_data = Path.home() / ".resonance"

    if subdir:
        path = app_data / subdir
    else:
        path = app_data

    # Create directory if it doesn't exist
    path.mkdir(parents=True, exist_ok=True)

    return str(path)


def is_bundled():
    """
    Check if running as a PyInstaller bundle.

    Returns:
        True if running as bundled EXE, False if running as script
    """
    return hasattr(sys, '_MEIPASS')
