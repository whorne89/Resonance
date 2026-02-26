# Post-Processing Design — Resonance
**Date:** 2026-02-26
**Status:** Approved

---

## Overview

Add a local LLM-based post-processor that runs after Whisper transcription. It cleans up grammar, fixes punctuation, and intelligently interprets spoken formatting commands (bullets, numbered lists, new lines, "scratch that", etc.) — all on-device, no cloud.

---

## Goals

- Grammar and punctuation correction on every transcription
- Intelligent interpretation of spoken formatting commands (bullets, numbered lists, line breaks, corrections)
- Fully local — no internet required after model download
- Toggleable — can be disabled with zero overhead
- Unified device setting (CPU or GPU) that applies to both Whisper and the grammar LLM

---

## Architecture

### Pipeline (unchanged flow, new step added)

```
Record audio
  → Whisper transcription (QThread)
  → apply_dictionary()
  → PostProcessor.process()   ← NEW
  → type_text()
```

All steps run inside the existing `TranscriptionWorker` QThread. No new threads needed.

### New module: `src/core/post_processor.py`

Mirrors the structure of `transcriber.py`:
- Lazy-loads the GGUF model at first use
- Holds model in memory for subsequent calls
- Thread-safe via `threading.Lock`
- `process(text: str) -> str` — returns corrected text, or original text on failure
- Failure never blocks output (silent fallback)

---

## Model

**Model:** Qwen2.5-0.5B-Instruct (Q4_K_M quantization)
**Size:** ~400MB
**Source:** `Qwen/Qwen2.5-0.5B-Instruct-GGUF` on HuggingFace
**Download:** `huggingface_hub.hf_hub_download()` — same mechanism as Whisper models
**Storage:** `.resonance/models/llm/qwen2.5-0.5b-instruct-q4_k_m.gguf`

**Framework:** `llama-cpp-python`
- CPU mode: `n_gpu_layers=0`
- GPU mode: `n_gpu_layers=-1` (full offload to CUDA/Metal)

---

## Prompt

```
You are a transcription post-processor. Your job is to:
1. Fix grammar and punctuation
2. Intelligently interpret spoken formatting commands and apply them

Examples of formatting commands to handle:
- "bullet" / "bullets" → format items as a markdown bullet list
- "new line" / "next line" → insert a line break
- "number one ... number two ..." → format as a numbered list
- "scratch that" / "delete that" → remove the preceding content
- "period" / "comma" / "colon" → insert the punctuation

Output only the final corrected text. No explanations, no commentary.

Text: {raw_text}
Corrected:
```

The LLM is intelligent enough to handle variations — these are guidelines, not exhaustive rules.

---

## Config Changes

### New unified device setting

Replaces `whisper.device`. Both Whisper and the LLM read from this.

```json
"processing": {
  "device": "cpu"
}
```

`"cpu"` or `"cuda"`. Whisper's `compute_type` stays Whisper-specific.

### New post-processing section

```json
"post_processing": {
  "enabled": false,
  "model": "qwen2.5-0.5b-instruct-q4_k_m.gguf"
}
```

Default `enabled: false` — opt-in, since it requires a model download.

---

## Settings UI Changes

1. **Processing Device** — replaces current `whisper.device` field
   Radio buttons: `CPU` | `GPU (CUDA)` (GPU grayed out if CUDA unavailable)

2. **Post-Processing toggle** — checkbox: "Enable grammar & punctuation correction"
   When off, `PostProcessor.process()` is skipped entirely.

3. **Grammar Model section** (visible when post-processing enabled)
   - Status: "Not downloaded" / "Downloading... 45%" / "Ready"
   - "Download Model" button (~400MB, one-time)

---

## Performance Expectations

| Hardware | Expected added latency (typical utterance) |
|---|---|
| Nvidia 3080 (GPU mode) | ~100–300ms |
| Modern CPU only | ~500ms–1.5s |
| Apple Silicon | ~200–400ms (Metal) |

---

## Future Extensions (not in scope now)

- Audio/visual recording cues (sound on start, sound on stop, processing indicator)
- Larger model option (1.5B) for better formatting accuracy
- Per-app context profiles (coding vs. prose vs. email)

---

## Out of Scope

- Cloud API fallback
- Separate device settings per component
- "Type raw then correct in-place" — not needed, full corrected text is typed at once
