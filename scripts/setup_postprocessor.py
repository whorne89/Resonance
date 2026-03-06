#!/usr/bin/env python3
"""
Pre-download and set up the post-processor binaries and model for local development.

This script downloads llama-server and the Qwen GGUF model to the .resonance/
directory. Useful for developers to avoid first-run delays during testing.

Usage:
    python scripts/setup_postprocessor.py

Options:
    --no-model      Skip GGUF model download (binary only)
    --no-binary     Skip binary download (model only)
"""

import os
import sys
import argparse
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.post_processor import PostProcessor


def main():
    parser = argparse.ArgumentParser(
        description="Pre-download post-processor binaries and model"
    )
    parser.add_argument(
        "--no-model",
        action="store_true",
        help="Skip downloading GGUF model"
    )
    parser.add_argument(
        "--no-binary",
        action="store_true",
        help="Skip downloading llama-server binary"
    )
    args = parser.parse_args()

    processor = PostProcessor()

    print("\n" + "=" * 70)
    print("Post-Processor Setup")
    print("=" * 70)

    # Check what's already downloaded
    bin_exists = os.path.isfile(processor._get_llama_server_exe())
    model_exists = os.path.isfile(processor._get_gguf_model_path())

    print(f"\nBinary: {'cached' if bin_exists else 'missing'}")
    print(f"Model:  {'cached' if model_exists else 'missing'}")

    # Download what's needed
    print("\n" + "-" * 70)

    if not bin_exists and not args.no_binary:
        print("Downloading llama-server binary...")
        try:
            processor.download_model(progress_callback=_progress_callback)
            print("\nBinary downloaded successfully")
        except Exception as e:
            print(f"\nBinary download failed: {e}")
            return 1

    if not model_exists and not args.no_model:
        print("Downloading Qwen GGUF model (~1.1 GB)...")
        try:
            processor.download_model(progress_callback=_progress_callback)
            print("\nModel downloaded successfully")
        except Exception as e:
            print(f"\nModel download failed: {e}")
            return 1

    # Verify
    print("\n" + "-" * 70)
    if os.path.isfile(processor._get_llama_server_exe()):
        print(f"Binary: {processor._get_llama_server_exe()}")
    if os.path.isfile(processor._get_gguf_model_path()):
        print(f"Model:  {processor._get_gguf_model_path()}")

    print("\n" + "=" * 70)
    print("Setup complete! Post-processing is ready to use.")
    print("=" * 70 + "\n")

    return 0


def _progress_callback(downloaded, total):
    """Show download progress."""
    if total > 0:
        percent = (downloaded / total) * 100
        mb_downloaded = downloaded / (1024 * 1024)
        mb_total = total / (1024 * 1024)
        print(
            f"\r  Progress: {percent:.1f}% ({mb_downloaded:.0f}MB / {mb_total:.0f}MB)",
            end="",
            flush=True
        )


if __name__ == "__main__":
    sys.exit(main())
