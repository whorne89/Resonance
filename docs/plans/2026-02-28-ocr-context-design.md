# OCR Screen Context — Design Document

## Overview

Add screen context awareness to Resonance. When the user presses the hotkey, OCR captures the active window text in parallel with recording. This context feeds into two places:

1. **Whisper `initial_prompt`** — proper nouns/names from the screen bias transcription spelling
2. **Post-processor system prompt** — app-type-specific prompt swapped in for tone-appropriate cleanup

OCR is a separate toggle in Settings. It requires post-processing to be enabled.

## Architecture

### New module: `src/core/screen_context.py`

```
ScreenContextEngine
  ├── capture()              → ScreenContext (runs full pipeline)
  ├── _capture_window()      → PIL Image (mss + win32gui)
  ├── _extract_text(image)   → str (winocr)
  ├── _detect_app_type(text, title) → AppType enum
  └── _extract_proper_nouns(text)   → list[str]

ScreenContext (dataclass)
  ├── raw_text: str
  ├── app_type: AppType
  ├── proper_nouns: list[str]
  └── window_title: str

AppType (enum)
  ├── CHAT
  ├── EMAIL
  ├── CODE
  ├── DOCUMENT
  └── GENERAL
```

### Dependencies

- `winocr` — Windows native OCR (~5-10 MB, uses built-in Windows OCR engine)
- `mss` — Screenshot capture (~24 KB, pure Python, zero deps)
- Both are lightweight, offline, no external binaries

### Pipeline Flow

```
Hotkey PRESSED
  ├── play start tone
  ├── start audio recording
  └── fire ScreenContextEngine.capture() in background thread
        ├── get foreground window rect + title (win32gui, ~1ms)
        ├── capture window screenshot (mss, ~3ms)
        ├── run OCR (winocr, ~50ms)
        ├── detect app type from title + OCR text (~1ms)
        └── extract proper nouns from OCR text (~1ms)
        Total: ~56ms, stored as self.current_context

User speaks (1-30 seconds)...
  └── OCR finished long ago, result in memory

Hotkey RELEASED
  ├── stop audio recording
  ├── retrieve self.current_context (already done)
  ├── build Whisper initial_prompt from proper_nouns
  ├── Whisper transcribes with initial_prompt
  ├── select system prompt based on app_type
  └── Qwen post-processes with app-type prompt
```

Zero added latency — OCR runs in parallel with recording.

---

## App Type Detection (Python heuristics)

```python
def _detect_app_type(self, ocr_text: str, window_title: str) -> AppType:
    title = window_title.lower()

    # Chat apps
    chat_keywords = ["slack", "discord", "teams", "telegram", "whatsapp",
                     "messenger", "signal", "imessage", "groupme"]
    if any(k in title for k in chat_keywords):
        return AppType.CHAT

    # Email
    email_title_keywords = ["outlook", "gmail", "mail", "thunderbird", "protonmail"]
    if any(k in title for k in email_title_keywords):
        return AppType.EMAIL
    email_ocr_keywords = ["subject:", "to:", "cc:", "bcc:", "from:"]
    if any(k in ocr_text.lower() for k in email_ocr_keywords):
        return AppType.EMAIL

    # Code editors
    code_keywords = ["visual studio", "vscode", "code -", "pycharm", "intellij",
                     "vim", "neovim", "sublime", "atom", "cursor", "zed"]
    if any(k in title for k in code_keywords):
        return AppType.CODE

    # Document editors
    doc_keywords = ["word", "google docs", "notion", "obsidian", "notepad",
                    "libreoffice", "pages"]
    if any(k in title for k in doc_keywords):
        return AppType.DOCUMENT

    return AppType.GENERAL
```

---

## Proper Noun Extraction

Simple heuristic approach — extract capitalized words from OCR text that look like names:

```python
def _extract_proper_nouns(self, ocr_text: str) -> list[str]:
    """Extract likely proper nouns from OCR text."""
    # Common words to exclude (UI elements, common English)
    common_upper = {"I", "OK", "AM", "PM", "US", "TV", "IT", "ID",
                    "The", "This", "That", "Here", "There", "Yes", "No",
                    "New", "Open", "Save", "Close", "File", "Edit", "View",
                    "Help", "Home", "Back", "Next", "Send", "Reply",
                    "Delete", "Settings", "Search", "Menu", "Type"}

    words = ocr_text.split()
    proper_nouns = []
    seen = set()

    for word in words:
        # Strip punctuation
        clean = word.strip(".,!?:;\"'()[]{}")
        if not clean or len(clean) < 2:
            continue
        # Must start with uppercase, not be ALL CAPS (unless short like a name)
        if clean[0].isupper() and clean not in common_upper:
            if not clean.isupper() or len(clean) <= 4:
                lower = clean.lower()
                if lower not in seen:
                    seen.add(lower)
                    proper_nouns.append(clean)

    return proper_nouns[:30]  # Cap at 30 to stay under token limit
```

---

## Whisper Prompt Construction

Based on research, natural sentences work better than comma lists, and important terms should be placed at the end.

```python
def build_whisper_prompt(proper_nouns: list[str], app_type: AppType) -> str:
    """Build a natural-language initial_prompt for Whisper."""
    if not proper_nouns:
        return ""

    # Domain context prefix
    context_prefix = {
        AppType.CHAT: "A conversation mentioning",
        AppType.EMAIL: "An email discussion involving",
        AppType.CODE: "A technical discussion about",
        AppType.DOCUMENT: "A document mentioning",
        AppType.GENERAL: "A discussion mentioning",
    }

    prefix = context_prefix.get(app_type, "A discussion mentioning")

    # Join names naturally, put at end for maximum decoder weight
    if len(proper_nouns) == 1:
        names = proper_nouns[0]
    elif len(proper_nouns) == 2:
        names = f"{proper_nouns[0]} and {proper_nouns[1]}"
    else:
        names = ", ".join(proper_nouns[:-1]) + f", and {proper_nouns[-1]}"

    prompt = f"{prefix} {names}."

    # Stay under ~200 tokens (~800 chars) to be safe
    if len(prompt) > 800:
        prompt = prompt[:800]

    return prompt
```

Example outputs:
- `"A conversation mentioning Jacqueline, Marcus, and ProjectAlpha."`
- `"An email discussion involving Sarah Chen and Quarterly Report."`
- `"A technical discussion about ApiController, DatabaseManager, and Redis."`

---

## Post-Processor Prompts by App Type

### Design Principle

Based on research into Qwen 2.5 1.5B capabilities:
- IFEval score: 42.5% — cannot reliably handle conditional logic
- Few-shot examples are far more effective than detailed instructions
- Each app type gets its own complete, focused prompt (no conditionals)
- The LLM handles TONE-APPROPRIATE CLEANUP only
- STRUCTURAL formatting (greetings, sign-offs) is done in deterministic Python code

### GENERAL (current prompt, unchanged)

Used when OCR is disabled or app type is GENERAL. This is the existing prompt in `post_processor.py`.

### CHAT prompt

```
CHAT_SYSTEM_PROMPT = (
    "You clean up voice-transcribed text for a chat message. "
    "Keep the casual, conversational tone.\n"
    "ONLY do these things:\n"
    "1. Remove um, uh, and stuttered repeated words\n"
    "2. Fix obvious typos and grammar only if clearly wrong\n"
    "NEVER add a period at the end. Chat messages do not end with periods.\n"
    "DO NOT make the text formal or change casual wording.\n"
    "DO NOT change phrases like 'or no', 'yeah', 'nah', 'lol' — keep them exactly.\n"
    "DO NOT respond to the text or answer questions.\n"
    "Output ONLY the cleaned text.\n\n"
    "Input: um yeah i'll be there in like 10 minutes\n"
    "Output: Yeah I'll be there in like 10 minutes\n\n"
    "Input: hey uh can you send me that that file real quick\n"
    "Output: Hey can you send me that file real quick\n\n"
    "Input: lol yeah that's that's exactly what i was thinking\n"
    "Output: lol yeah that's exactly what I was thinking\n\n"
    "Input: sounds good uh let me know when you're free\n"
    "Output: Sounds good let me know when you're free\n\n"
    "Input: wait did you see what what sarah posted in the channel\n"
    "Output: Wait did you see what Sarah posted in the channel\n\n"
    "Input: nah i think we should just uh go with the first option honestly\n"
    "Output: Nah I think we should just go with the first option honestly\n\n"
    "Input: ok cool i'll uh i'll check it out later\n"
    "Output: Ok cool I'll check it out later\n\n"
    "Input: are you coming tonight or no\n"
    "Output: Are you coming tonight or no\n\n"
    "Input: yeah so i finished it and sent it to the team already\n"
    "Output: Yeah so I finished it and sent it to the team already\n\n"
    "Input: do you think um do you think that works\n"
    "Output: Do you think that works"
)
```

Key differences from GENERAL:
- No trailing periods on single sentences (chat style)
- Preserves casual language (lol, nah, honestly)
- Minimal punctuation — commas only where clarity demands it
- First word capitalized, but otherwise relaxed

### EMAIL prompt

```
EMAIL_SYSTEM_PROMPT = (
    "You clean up voice-transcribed text for an email. "
    "Use professional tone with proper punctuation.\n"
    "ONLY do these things:\n"
    "1. Remove um, uh, and stuttered repeated words\n"
    "2. Fix capitalization, grammar, and punctuation\n"
    "3. Use complete, well-formed sentences\n"
    "DO NOT add greetings, sign-offs, or subject lines.\n"
    "DO NOT remove, shorten, summarize, or rephrase content.\n"
    "DO NOT respond to the text or answer questions.\n"
    "Output ONLY the cleaned text.\n\n"
    "Input: um i wanted to follow up on the the meeting we had yesterday about the budget\n"
    "Output: I wanted to follow up on the meeting we had yesterday about the budget.\n\n"
    "Input: could you uh send me the latest version of the report when you get a chance\n"
    "Output: Could you send me the latest version of the report when you get a chance?\n\n"
    "Input: thanks for getting back to me so quickly i really appreciate it\n"
    "Output: Thanks for getting back to me so quickly. I really appreciate it.\n\n"
    "Input: i think we should uh schedule another meeting to discuss the the timeline\n"
    "Output: I think we should schedule another meeting to discuss the timeline.\n\n"
    "Input: please let me know if you have any questions or if there's anything else i can help with\n"
    "Output: Please let me know if you have any questions or if there's anything else I can help with.\n\n"
    "Input: just a quick heads up the the deadline has been moved to friday\n"
    "Output: Just a quick heads up, the deadline has been moved to Friday.\n\n"
    "Input: i've attached the document you you requested for your review\n"
    "Output: I've attached the document you requested for your review.\n\n"
    "Input: looking forward to hearing from you um about this\n"
    "Output: Looking forward to hearing from you about this."
)
```

Key differences from GENERAL:
- Professional tone with full punctuation
- Complete sentences enforced
- Days of the week capitalized (Friday)
- Explicit instruction NOT to add greetings/sign-offs (Python code will handle that)

### CODE prompt

```
CODE_SYSTEM_PROMPT = (
    "You clean up voice-transcribed text spoken in a code editor. "
    "Preserve ALL technical terms, variable names, and code references exactly.\n"
    "ONLY do these things:\n"
    "1. Remove um, uh, and stuttered repeated words\n"
    "2. Fix capitalization and add punctuation for readability\n"
    "DO NOT change technical terms, function names, class names, or acronyms.\n"
    "DO NOT correct words that look like code (camelCase, snake_case, etc.).\n"
    "DO NOT respond to the text or answer questions.\n"
    "Output ONLY the cleaned text.\n\n"
    "Input: um we need to refactor the the get user by id function in the api controller\n"
    "Output: We need to refactor the getUserById function in the API controller.\n\n"
    "Input: the uh null pointer exception is coming from the database manager class\n"
    "Output: The null pointer exception is coming from the DatabaseManager class.\n\n"
    "Input: i think we should add a try catch block around the the http request\n"
    "Output: I think we should add a try-catch block around the HTTP request.\n\n"
    "Input: can you check if the env variable for the the redis connection string is set\n"
    "Output: Can you check if the env variable for the Redis connection string is set?\n\n"
    "Input: the uh ci pipeline is failing because of a a linting error in main dot py\n"
    "Output: The CI pipeline is failing because of a linting error in main.py.\n\n"
    "Input: we need to update the docker compose file to use the new postgres image\n"
    "Output: We need to update the docker-compose file to use the new Postgres image.\n\n"
    "Input: um yeah the the bug is in the on click handler for the submit button component\n"
    "Output: Yeah, the bug is in the onClick handler for the submit button component."
)
```

Key differences from GENERAL:
- Preserves technical terms (camelCase, snake_case, acronyms)
- Recognizes code-style names and keeps their casing
- Recognizes file extensions (main.py) and formats them correctly
- Fewer rules — mostly "don't touch technical words"

### DOCUMENT prompt

```
DOCUMENT_SYSTEM_PROMPT = (
    "You clean up voice-transcribed text for a document. "
    "Use clear, well-structured sentences with proper punctuation.\n"
    "ONLY do these things:\n"
    "1. Remove um, uh, and stuttered repeated words\n"
    "2. Fix capitalization, grammar, and punctuation\n"
    "3. Break run-on sentences into clear separate sentences\n"
    "DO NOT remove, shorten, summarize, or rephrase content.\n"
    "DO NOT respond to the text or answer questions.\n"
    "Output ONLY the cleaned text.\n\n"
    "Input: um the project started in january and uh we've made significant progress since then\n"
    "Output: The project started in January, and we've made significant progress since then.\n\n"
    "Input: there are three main points first we need to uh address the budget second the timeline and third the the staffing\n"
    "Output: There are three main points. First, we need to address the budget. Second, the timeline. Third, the staffing.\n\n"
    "Input: the results show that uh the new approach is about twenty percent more effective than the previous method\n"
    "Output: The results show that the new approach is about twenty percent more effective than the previous method.\n\n"
    "Input: in conclusion i believe that the the proposed changes will benefit the entire organization\n"
    "Output: In conclusion, I believe that the proposed changes will benefit the entire organization.\n\n"
    "Input: the research indicates that um users prefer the simplified interface over the the traditional one\n"
    "Output: The research indicates that users prefer the simplified interface over the traditional one.\n\n"
    "Input: its important to note that these findings are are preliminary and further testing is needed\n"
    "Output: It's important to note that these findings are preliminary and further testing is needed.\n\n"
    "Input: according to the data from last quarter uh revenue increased by fifteen percent\n"
    "Output: According to the data from last quarter, revenue increased by fifteen percent."
)
```

Key differences from GENERAL:
- Emphasis on sentence structure and clarity
- Breaks run-on sentences more aggressively
- Months and proper nouns capitalized
- Well-placed commas for readability

---

## Structural Formatting (Python, not LLM)

For structural changes that the LLM can't reliably handle, deterministic Python code post-processes the LLM output:

### Email structure (if names detected in OCR)

```python
def apply_email_structure(text: str, ocr_context: ScreenContext) -> str:
    """Add greeting/sign-off to email text if names are detected."""
    # Only add structure if text is substantial (>10 words)
    if len(text.split()) < 10:
        return text

    # Try to find recipient name from OCR (look for "To:" field)
    recipient = extract_email_recipient(ocr_context.raw_text)

    # Don't add greeting if text already starts with one
    greetings = ["hi ", "hey ", "hello ", "dear ", "good morning", "good afternoon"]
    has_greeting = any(text.lower().startswith(g) for g in greetings)

    if recipient and not has_greeting:
        text = f"Hi {recipient},\n\n{text}"

    return text
```

### Chat formatting

```python
def apply_chat_formatting(text: str) -> str:
    """Ensure chat text doesn't feel overly formal."""
    # Chat messages never end with a period (single or multi-sentence)
    if text.endswith('.') and not text.endswith('...'):
        text = text[:-1]
    return text
```

Tested against live Qwen 2.5 1.5B — the model adds trailing periods ~40% of the time despite prompt instructions. This one-line fix catches all cases reliably. Questions (`?`) and exclamations (`!`) are unaffected. Ellipses (`...`) are preserved.

These are lightweight, predictable, and don't risk hallucination.

---

## Proper Noun Injection into OCR Context Prompt

When OCR detects names and post-processing is active, the proper nouns are also appended to the system prompt as a hint:

```python
def build_system_prompt(app_type: AppType, proper_nouns: list[str]) -> str:
    """Select system prompt and append proper noun hints."""
    prompts = {
        AppType.CHAT: CHAT_SYSTEM_PROMPT,
        AppType.EMAIL: EMAIL_SYSTEM_PROMPT,
        AppType.CODE: CODE_SYSTEM_PROMPT,
        AppType.DOCUMENT: DOCUMENT_SYSTEM_PROMPT,
        AppType.GENERAL: SYSTEM_PROMPT,
    }
    prompt = prompts.get(app_type, SYSTEM_PROMPT)

    if proper_nouns:
        names = ", ".join(proper_nouns[:15])
        prompt += (
            f"\n\nNames and terms visible on screen: {names}\n"
            "Use these exact spellings when they appear in the input."
        )

    return prompt
```

This gives Qwen a spelling reference without asking it to do complex reasoning.

---

## Settings Integration

- New checkbox in Settings: "Screen Context (OCR)" with description
- Requires post-processing to be enabled (checkbox disabled/grayed when PP is off)
- When enabled, recording overlay shows badge: "Screen Context: ON"
- Config key: `ocr.enabled` (boolean)

---

## Test Scenarios

### Chat (Slack)
| Input speech | OCR names | Expected output |
|---|---|---|
| "um yeah tell jacqueline i'll be there in 10" | Jacqueline, Marcus | "Yeah tell Jacqueline I'll be there in 10" |
| "hey uh can you check the the pr that marcus opened" | Jacqueline, Marcus | "Hey can you check the PR that Marcus opened" |
| "lol that's that's hilarious" | (none) | "Lol that's hilarious" |

### Email (Outlook)
| Input speech | OCR names | Expected output |
|---|---|---|
| "um i wanted to follow up on our conversation from yesterday about the the quarterly report" | Sarah Chen, Quarterly Report | "I wanted to follow up on our conversation from yesterday about the quarterly report." |
| "could you please uh send me the updated timeline by by friday" | (none) | "Could you please send me the updated timeline by Friday?" |

### Code (VS Code)
| Input speech | OCR names | Expected output |
|---|---|---|
| "the uh bug is in the get user handler in api controller dot py" | getUserHandler, ApiController | "The bug is in the getUserHandler in ApiController.py." |
| "we need to add um error handling for the the database connection timeout" | DatabasePool, ConnectionManager | "We need to add error handling for the database connection timeout." |

### Document (Google Docs)
| Input speech | OCR names | Expected output |
|---|---|---|
| "um the project kickoff meeting was held on february 15th and uh all stakeholders were present" | (none) | "The project kickoff meeting was held on February 15th, and all stakeholders were present." |

---

## Risk Mitigation

### Whisper hallucination from initial_prompt
- Risk: Prompt text leaking into transcript on near-silent audio
- Mitigation: Existing VAD filter strips silence. Post-processor length guard catches inflated output. If audio is empty/near-silent, skip Whisper entirely (already handled).

### Qwen formatting drift
- Risk: App-type prompts cause Qwen to be too aggressive with changes
- Mitigation: All prompts retain "DO NOT remove, shorten, summarize" rules. Existing 4-layer hallucination guards remain active. Few-shot examples anchor expected behavior.

### OCR noise
- Risk: Window contains non-text elements, icons, or garbled OCR output
- Mitigation: Proper noun extraction filters aggressively (excludes common UI words, short words, ALL-CAPS). App type detection falls back to GENERAL if no patterns match.

### Windows OCR language pack missing
- Risk: Non-English Windows may not have English OCR pack
- Mitigation: Graceful fallback — if OCR fails, log warning and continue without context. Feature degrades to standard (no-OCR) behavior.

---

## Dependencies Summary

| Package | Size | Purpose |
|---|---|---|
| `winocr` | ~5-10 MB | Windows native OCR engine wrapper |
| `mss` | ~24 KB | Screenshot capture |

Total added weight: ~10 MB. No external binaries. No model downloads.

---

## Prompt Testing Results (Qwen 2.5 1.5B q4_k_m, live llama-server)

Tested 18 scenarios across all 5 app types. Results:

### Summary: 11/18 exact match, 7 acceptable diffs

All diffs are either (a) minor stylistic variations that are grammatically correct, or (b) the CHAT trailing period issue handled by Python post-processing.

### CHAT findings
- **Trailing periods**: Qwen 1.5B has a strong punctuation bias and adds trailing periods even when instructed not to. Prompt reinforcement does not fix this. **Solution**: Python `apply_chat_formatting()` strips trailing periods deterministically after LLM processing.
- **Casual language preserved**: "or no", "lol", "nah" all preserved correctly after prompt refinement.
- **Name capitalization**: Works when names are in the noun hints. Acronyms like "PR" are not capitalized unless in hints.

### EMAIL findings
- **Excellent accuracy**: 3/4 exact match. One diff was splitting a long sentence into two — grammatically valid alternative.
- **Name spelling**: "Sarah Chen" correctly capitalized from noun hints.
- **Day capitalization**: "friday" → "Friday" handled correctly.

### CODE findings
- **Technical terms preserved**: getUserHandler, ApiController, .env file all handled correctly with noun hints.
- **One diff**: "docker-compose" → "Docker Compose" — both are valid naming conventions.

### DOCUMENT findings
- **Good accuracy**: 1/3 exact match. Diffs are stylistic: model uses two sentences where we expected a comma, or colon/semicolons instead of period-separated list items. All outputs are grammatically correct and well-structured.

### KEY DESIGN DECISION
The CHAT trailing period issue confirms that **Python post-processing is essential for CHAT mode**. The `apply_chat_formatting()` function in the design handles this reliably. The LLM does what it's good at (cleanup, filler removal, name capitalization), and Python handles what it can't (structural formatting rules like "no trailing period").
