# Bundling Tesseract OCR

## Overview

To make Resonance fully portable without requiring users to install Tesseract, we bundle the Tesseract binary and language data files directly in the PyInstaller build.

## Setup for Windows Build

1. **Download Tesseract for Windows**
   - Get the portable version from: https://digi.bib.uni-mannheim.de/tesseract/
   - Or use the installer and extract files from: `C:\Program Files\Tesseract-OCR\`

2. **Create tesseract directory in project root**

   ```
   tesseract/
     tesseract.exe           # Main binary
     tessdata/
       eng.traineddata       # English language data (required)
       eng.cube.*            # Optional cube files
       pdf.ttf               # Optional font for PDF output
   ```

3. **Required files**:
   - `tesseract.exe` (~2 MB)
   - `tessdata/eng.traineddata` (~4.8 MB for "best" model, or ~1.8 MB for "fast" model)
   - Any DLL dependencies (leptonica, libarchive, etc.) - check with Dependency Walker

4. **Build** - PyInstaller will automatically bundle these files via the updated spec

## Development vs Production

- **Development**: Uses system-installed Tesseract (user must install manually)
- **Production (EXE)**: Uses bundled Tesseract from `tesseract/` directory
- **Fallback**: If neither is available, OCR features gracefully disable

## Platform Support

- **Windows**: Fully bundled (no user installation needed)
- **Linux**: Recommend system package (`apt-get install tesseract-ocr`) - bundling is complex due to library dependencies
- **macOS**: Recommend Homebrew (`brew install tesseract`) - or use static build

## Alternative: Static Builds

For cross-platform bundling, consider static-linked Tesseract builds:

- https://github.com/tesseract-ocr/tesseract/wiki/Compiling-%E2%80%93-GitInstallation

These have fewer runtime dependencies and are easier to bundle on Linux/macOS.
