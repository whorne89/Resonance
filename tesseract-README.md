# Tesseract Directory

This directory is for bundling Tesseract OCR with the Windows EXE build.

## Required Structure

```
tesseract/
  tesseract.exe           # Tesseract OCR executable (~2 MB)
  tessdata/
    eng.traineddata       # English language data (~4.8 MB for "best", ~1.8 MB for "fast")
```

## Setup Instructions

### Option 1: Download from Official Source

1. Go to https://github.com/UB-Mannheim/tesseract/wiki
2. Download the Windows installer for Tesseract 5.x
3. Install or extract the portable version
4. Copy the required files to this directory:
   - From `C:\Program Files\Tesseract-OCR\tesseract.exe` → `tesseract/tesseract.exe`
   - From `C:\Program Files\Tesseract-OCR\tessdata\eng.traineddata` → `tesseract/tessdata/eng.traineddata`

### Option 2: Use Helper Script

Run the included script (partially implemented):

```bash
python scripts/download_tesseract.py
```

## Building

Once the files are in place, PyInstaller will automatically bundle them:

```bash
pyinstaller resonance.spec -y
```

The bundled app will have Tesseract in `dist/Resonance/_internal/tesseract/` and will work without users needing to install anything.

## Platform Notes

- **Windows**: Fully bundled in EXE (this directory)
- **Linux**: Users must install via `apt-get install tesseract-ocr`
- **macOS**: Users must install via `brew install tesseract`

Bundling on Linux/macOS is complex due to dynamic library dependencies. The system package approach is recommended for those platforms.
