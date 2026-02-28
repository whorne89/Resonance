# Post-Processor: Grammar, Punctuation & Filler Cleanup

## Goal
Re-add LLM post-processing to clean up Whisper transcription output.
Scope is narrower than the previous attempt (no formatting commands).

## What it does
- Fix capitalization (sentence starts, proper nouns)
- Fix punctuation (periods, commas, question marks)
- Fix minor grammar errors
- Remove filler words (um, uh, like, you know, so, etc.)

## Backend
- **llama-server** subprocess on `localhost:8787`
- **Model:** Qwen 2.5 0.5B Instruct GGUF (q4_k_m, ~400 MB)
- Downloads llama-server binary + GGUF model on first enable
- Lazy start: server subprocess starts on first `.process()` call
- Stays running for app lifetime, killed on quit or toggle-off

## Lifecycle (tied to settings checkbox)

| Event | ON | OFF |
|-------|-----|------|
| App startup | `PostProcessor()` created | `None`, nothing runs |
| Settings toggle ON | Create `PostProcessor()` | - |
| Settings toggle OFF | - | `.shutdown()` kills server, set `None` |
| App quit | `.shutdown()` | Nothing |
| Transcription | Worker calls `.process(text)` | Worker skips |

## Pipeline placement
```
Whisper → PostProcessor.process(text) → DictionaryProcessor.apply() → KeyboardTyper
```
Post-processing runs inside `TranscriptionWorker` QThread.
Overlay stays in "processing" state until everything completes.

## Settings UI
Under "Speech Recognition" group, below the quality tier descriptions:
- Checkbox: "Post-processing"
- Inline description: "Clean up grammar, punctuation, and filler words"
- First enable triggers model download dialog if not yet downloaded

## System prompt
```
You clean up voice-to-text transcriptions. Fix grammar, punctuation,
and capitalization. Remove filler words (um, uh, like, you know).
Output ONLY the corrected text, nothing else.

Input: um so i went to the store and uh i bought some eggs
Output: I went to the store and bought some eggs.

Input: like do you think that we should you know go to the meeting
Output: Do you think that we should go to the meeting?

Input: the the project is uh almost done i think
Output: The project is almost done, I think.
```

## Files to create/modify
- **Create:** `src/core/post_processor.py` — PostProcessor class (llama-server only, no ONNX)
- **Modify:** `src/main.py` — init/shutdown/toggle PostProcessor, pass to TranscriptionWorker
- **Modify:** `src/gui/settings_dialog.py` — checkbox + model download trigger
- **Modify:** `src/utils/config.py` — get/set post-processing enabled/backend

## Differences from previous attempt
- No formatting commands (bullet, new line, scratch that)
- No ONNX backend (llama-server only, simpler code)
- Simpler system prompt (grammar/punctuation/filler only)
- Future: OCR screen context integration (separate phase)
