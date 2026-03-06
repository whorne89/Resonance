#!/usr/bin/env python3
"""
Download and extract Tesseract OCR for bundling with Resonance.

This script downloads the portable Tesseract build for Windows and extracts
the necessary files to the tesseract/ directory for PyInstaller bundling.

Run before building the EXE:
    python scripts/download_tesseract.py
"""

import os
import sys
import urllib.request
import zipfile
import shutil
from pathlib import Path

# Tesseract 5.x Windows build (portable)
TESSERACT_VERSION = "5.3.3"
TESSERACT_URL = f"https://digi.bib.uni-mannheim.de/tesseract/tesseract-ocr-w64-setup-{TESSERACT_VERSION}.20231005.exe"

# Alternative: Use pre-extracted portable build
PORTABLE_URL = "https://github.com/UB-Mannheim/tesseract/releases/download/v5.3.3/tesseract-ocr-setup-5.3.3-20231005.exe"

PROJECT_ROOT = Path(__file__).parent.parent
TESSERACT_DIR = PROJECT_ROOT / "tesseract"
TESSDATA_DIR = TESSERACT_DIR / "tessdata"


def download_file(url, dest):
    """Download a file with progress indication."""
    print(f"Downloading {url}...")
    with urllib.request.urlopen(url) as response:
        total_size = int(response.headers.get('Content-Length', 0))
        downloaded = 0
        chunk_size = 8192
        
        with open(dest, 'wb') as f:
            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if total_size > 0:
                    percent = (downloaded / total_size) * 100
                    print(f"\rProgress: {percent:.1f}% ({downloaded}/{total_size} bytes)", end='')
        print()


def setup_manual_instructions():
    """Print manual setup instructions if automated download fails."""
    print("\n" + "="*70)
    print("MANUAL SETUP REQUIRED")
    print("="*70)
    print("\nAutomatic download is not implemented. Please set up manually:\n")
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
    print("Tesseract will be bundled automatically by PyInstaller.")
    print("="*70)


def main():
    """Set up Tesseract for bundling."""
    if TESSERACT_DIR.exists():
        response = input(f"\n{TESSERACT_DIR} already exists. Overwrite? [y/N]: ")
        if response.lower() != 'y':
            print("Cancelled.")
            return
        shutil.rmtree(TESSERACT_DIR)
    
    TESSERACT_DIR.mkdir(parents=True, exist_ok=True)
    TESSDATA_DIR.mkdir(parents=True, exist_ok=True)
    
    # For now, just print instructions
    # TODO: Implement actual extraction from Tesseract installer
    setup_manual_instructions()
    
    # Create a README in the tesseract directory
    readme_path = TESSERACT_DIR / "README.txt"
    with open(readme_path, 'w') as f:
        f.write("Tesseract OCR for Resonance\n")
        f.write("=" * 50 + "\n\n")
        f.write("This directory contains Tesseract OCR files for bundling.\n\n")
        f.write("Required structure:\n")
        f.write("  tesseract/\n")
        f.write("    tesseract.exe          - Main executable\n")
        f.write("    tessdata/\n")
        f.write("      eng.traineddata      - English language data\n\n")
        f.write(f"Source: https://github.com/UB-Mannheim/tesseract/wiki\n")
        f.write(f"Version: {TESSERACT_VERSION} or newer\n")
    
    print(f"\nCreated {TESSERACT_DIR} directory structure.")
    print(f"Follow the instructions above to complete setup.\n")


if __name__ == '__main__':
    main()
