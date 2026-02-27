# Post-Processing Design

**Date:** 2026-02-27
**Status:** Approved

## Goal

Add a lightweight, local post-processing step after Whisper transcription (tiny model) to:
1. Fix punctuation, capitalization, and minor grammar errors
2. Correct small transcription mistakes
3. Interpret spoken formatting commands ("new line", "bullet", "scratch that", "period", etc.)

## Constraints

- Local only — no cloud APIs, no internet required
- Cross-platform — must work on Windows, macOS, Linux
- Fast — post-processing overhead should be minimal on top of tiny model's sub-second transcription
- Lightweight — avoid massive dependencies (e.g., PyTorch)

## Architecture

Pipeline: `Audio → Transcriber (tiny) → PostProcessor → Dictionary → KeyboardTyper`

### PostProcessor class (`src/core/post_processor.py`)

```python
class PostProcessor:
    def __init__(self, backend="onnx"):  # or "llama-server"
    def load_model(self): ...
    def process(self, raw_text: str) -> str: ...
    def is_model_downloaded(self) -> bool: ...
    def download_model(self): ...
```

### Backend 1 — onnxruntime-genai (`onnx`)

- Package: `onnxruntime-genai` (pre-built wheels on PyPI for Win/Mac/Linux, Python 3.12)
- Model: Qwen2.5-0.5B-Instruct INT4 ONNX (~350 MB)
- Runs in-process, no external binaries
- Estimated speed: ~3-5s for 50 tokens (needs benchmarking)

### Backend 2 — llama-server subprocess (`llama-server`)

- Binary: `llama-server` from llama.cpp releases (pre-built for all platforms)
- Model: Qwen2.5-0.5B-Instruct Q4_K_M GGUF (~280 MB)
- Runs as managed background HTTP process
- Estimated speed: ~1.5-3s for 50 tokens (needs benchmarking)

### System prompt

```
You are a transcription post-processor. Your job is to:
1. Fix grammar, punctuation, and capitalization
2. Intelligently interpret spoken formatting commands and apply them

Examples of formatting commands to handle:
- "bullet" / "bullets" → format items as a markdown bullet list
- "new line" / "next line" → insert a line break
- "number one ... number two ..." → format as a numbered list
- "scratch that" / "delete that" → remove the preceding content
- "period" / "comma" / "colon" → insert the punctuation
- "page break" → insert a page break

Output only the final corrected text. No explanations, no commentary.
```

## Integration

- `TranscriptionWorker.run()` calls `post_processor.process(text)` after transcription
- Post-processing is optional, toggled via `post_processing.enabled` setting
- Model stays loaded in memory (lazy load on first use)

## Settings UI

- Toggle: "Enable post-processing"
- Model download button
- Backend selector (future, once benchmarks determine winner)

## Benchmarking plan

Before full integration, create a benchmark script that:
1. Installs both `onnxruntime-genai` and downloads `llama-server`
2. Runs the same 5 sample transcriptions through each backend
3. Reports: latency per call, output quality, memory usage
4. Winner becomes the default backend

## Previous work

- `feat/post-processing` branch used `llama-cpp-python` with Qwen2.5-0.5B GGUF — abandoned due to no pre-built Python 3.12 Windows wheels
- Same system prompt and general approach, different backend
