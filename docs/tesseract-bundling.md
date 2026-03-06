# Bundling Tesseract OCR

## Overview

On Windows, Resonance uses the native Windows OCR engine (winocr) by default, so Tesseract bundling is only needed if you want to use Tesseract on Windows instead.

On Linux/macOS, Tesseract should be installed via the system package manager — bundling is not recommended due to dynamic library dependencies.

## Windows EXE Bundling (Optional)

If you want to bundle Tesseract for Windows distribution:

1. **Download Tesseract for Windows**
   - Get the portable version from: https://digi.bib.uni-mannheim.de/tesseract/
   - Or use the installer and extract files from: `C:\Program Files\Tesseract-OCR\`

2. **Create tesseract directory in project root**

   ```
   tesseract/
     tesseract.exe           # Main binary
     tessdata/
       eng.traineddata       # English language data (required)
   ```

3. **Required files**:
   - `tesseract.exe` (~2 MB)
   - `tessdata/eng.traineddata` (~4.8 MB for "best" model, or ~1.8 MB for "fast" model)

4. **Build** — PyInstaller will automatically bundle these files via the updated spec

## Platform Support

| Platform | OCR Engine | Setup |
|----------|-----------|-------|
| **Windows** | winocr (native) | No setup needed |
| **Linux** | Tesseract | `sudo apt-get install tesseract-ocr` |
| **macOS** | Tesseract | `brew install tesseract` |

## Development vs Production

- **Development (Windows)**: Uses built-in Windows OCR — no Tesseract needed
- **Development (Linux/macOS)**: Install Tesseract via package manager
- **Production EXE (Windows)**: Uses built-in Windows OCR — Tesseract bundling optional
- **Fallback**: If OCR engine is unavailable, OCR features gracefully disable
