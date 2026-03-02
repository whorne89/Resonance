"""
Resource path utilities for Resonance.
Handles path resolution for both development and PyInstaller bundled EXE.
"""

import sys
from pathlib import Path


def _get_app_root():
    """
    Get the root directory of the application.

    When running as a bundled EXE, returns the directory containing the .exe.
    When running as a script, returns the project root (parent of src/).

    Returns:
        Path to the application root directory
    """
    if hasattr(sys, '_MEIPASS'):
        # Running as bundled exe - use the directory where the .exe lives
        return Path(sys.executable).parent
    else:
        # Running as script - src/utils/resource_path.py -> go up two levels to project root
        return Path(__file__).parent.parent.parent


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
        base_path = Path(sys._MEIPASS) / 'resources'
    else:
        # Running as script - resources are in src/resources/
        base_path = Path(__file__).parent.parent / 'resources'

    if relative_path:
        return str(base_path / relative_path)
    return str(base_path)


def get_app_data_path(subdir=""):
    """
    Get path to application data directory (for user-writable data like models).

    Stores data relative to the application directory so everything stays
    on the same drive as the application.

    Args:
        subdir: Subdirectory within app data (e.g., "models", "cache")

    Returns:
        Absolute path to the app data directory
    """
    app_data = _get_app_root() / ".resonance"

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
