# whisper.cpp + Vulkan GPU Migration Design

## Goal
Replace faster-whisper with pywhispercpp. Add GPU toggle with Vulkan detection and guided install flow.

## GPU Detection Flow (settings dialog)
1. Default: CPU selected
2. User clicks GPU →
   - Check `vulkan-1.dll` loadable?
     - YES → "GPU ready" (green) ✓
     - NO → Check GPU presence (display adapter detection)
       - GPU found → "Your GPU is compatible. Install Vulkan runtime to enable GPU mode." + "Open Download Page" button + "Check Again" button
       - No GPU → "No compatible GPU detected." GPU option disabled.

## Files Changed
- `transcriber.py` — rewrite for pywhispercpp API (same class interface)
- `settings_dialog.py` — GPU toggle with Vulkan detection flow
- `pyproject.toml` — swap faster-whisper → pywhispercpp

## Model Names (GGML format)
- tiny, base, small, medium, large-v3
- distil-whisper: TBD (verify GGML availability)

## What stays the same
- Transcriber class interface (init, transcribe, change_model, change_device)
- Config format (whisper.device = "cpu" or "gpu")
- main.py, audio, hotkeys, typing, dictionary — untouched
