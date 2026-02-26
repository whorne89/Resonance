"""
Logging configuration for Resonance.
Provides file-based logging for debugging and error tracking.
"""

import logging
import os
from pathlib import Path
from logging.handlers import RotatingFileHandler

from utils.resource_path import get_app_data_path


def setup_logger(name="Resonance", log_dir=None, level=logging.INFO):
    """
    Set up application logger with file rotation.

    Args:
        name: Logger name (default "Resonance")
        log_dir: Directory for log files (default: <app_root>/.resonance/logs/)
        level: Logging level (default: INFO)

    Returns:
        Configured logger instance
    """
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid duplicate handlers
    if logger.handlers:
        return logger

    # Determine log directory
    if log_dir is None:
        log_dir = Path(get_app_data_path("logs"))
    else:
        log_dir = Path(log_dir)

    # Create log directory if it doesn't exist
    log_dir.mkdir(parents=True, exist_ok=True)

    # Log file path
    log_file = log_dir / "resonance.log"

    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # File handler with rotation (max 5MB per file, keep 3 backup files)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Console handler for warnings and errors
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    logger.info(f"Logger initialized. Log file: {log_file}")

    return logger


def get_logger(name="Resonance"):
    """
    Get or create a logger instance.

    Args:
        name: Logger name

    Returns:
        Logger instance
    """
    logger = logging.getLogger(name)

    # If logger not yet configured, set it up
    if not logger.handlers:
        return setup_logger(name)

    return logger
