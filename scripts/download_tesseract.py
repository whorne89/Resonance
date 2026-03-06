#!/usr/bin/env python3
"""
Download and extract Tesseract OCR for bundling with Resonance (Windows EXE only).

On Linux/macOS, Tesseract should be installed via package manager instead:
    Linux:  sudo apt-get install tesseract-ocr
    macOS:  brew install tesseract

This script sets up the tesseract/ directory for PyInstaller bundling on Windows.

Run before building the EXE:
    python scripts/download_tesseract.py
"""

import os
import shutil
from pathlib import Path

TESSERACT_VERSION = "5.3.3"

PROJECT_ROOT = Path(__file__).parent.parent
TESSERACT_DIR = PROJECT_ROOT / "tesseract"
TESSDATA_DIR = TESSERACT_DIR / "tessdata"


def setup_instructions():
    """Print manual setup instructions."""
    print("\n" + "=" * 70)
    print("TESSERACT SETUP (Windows EXE bundling only)")
    print("=" * 70)
    print()
    print("1. Download Tesseract for Windows:")
    print("   https://github.com/UB-Mannheim/tesseract/wiki")
    print()
    print("2. Install Tesseract (or extract portable version)")
    print()
    print("3. Copy these files to the project:")
    print(f"   {TESSERACT_DIR}/")
    print("     tesseract.exe")
    print("     tessdata/")
    print("       eng.traineddata")
    print()
    print("4. Required files from Tesseract installation:")
    print("   - tesseract.exe (~2 MB)")
    print("   - tessdata/eng.traineddata (~4.8 MB)")
    print()
    print("PyInstaller will bundle these automatically via resonance.spec.")
    print()
    print("NOTE: On Linux/macOS, use system packages instead:")
    print("  Linux:  sudo apt-get install tesseract-ocr")
    print("  macOS:  brew install tesseract")
    print("=" * 70)


def main():
    """Set up Tesseract directory for bundling."""
    if TESSERACT_DIR.exists():
        response = input(f"\n{TESSERACT_DIR} already exists. Overwrite? [y/N]: ")
        if response.lower() != 'y':
            print("Cancelled.")
            return
        shutil.rmtree(TESSERACT_DIR)

    TESSERACT_DIR.mkdir(parents=True, exist_ok=True)
    TESSDATA_DIR.mkdir(parents=True, exist_ok=True)

    # Create a README in the tesseract directory
    readme_path = TESSERACT_DIR / "README.txt"
    with open(readme_path, 'w') as f:
        f.write("Tesseract OCR for Resonance\n")
        f.write("=" * 50 + "\n\n")
        f.write("This directory contains Tesseract OCR files for Windows EXE bundling.\n\n")
        f.write("Required structure:\n")
        f.write("  tesseract/\n")
        f.write("    tesseract.exe          - Main executable\n")
        f.write("    tessdata/\n")
        f.write("      eng.traineddata      - English language data\n\n")
        f.write(f"Source: https://github.com/UB-Mannheim/tesseract/wiki\n")
        f.write(f"Version: {TESSERACT_VERSION} or newer\n")

    print(f"\nCreated {TESSERACT_DIR} directory structure.")
    setup_instructions()


if __name__ == '__main__':
    main()
