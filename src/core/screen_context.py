"""
Screen context module for OCR-based awareness.
Captures the active window, extracts text via Windows native OCR,
detects the app type, and extracts proper nouns for Whisper hints.
"""

import ctypes
import ctypes.wintypes
from dataclasses import dataclass, field
from enum import Enum

from utils.logger import get_logger


class AppType(Enum):
    CHAT = "chat"
    EMAIL = "email"
    CODE = "code"
    DOCUMENT = "document"
    GENERAL = "general"


@dataclass
class ScreenContext:
    raw_text: str
    app_type: AppType
    proper_nouns: list = field(default_factory=list)
    window_title: str = ""


# ── App-type system prompts (tested against Qwen 2.5 1.5B) ──────────

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

# Prompt map for build_system_prompt
_APP_TYPE_PROMPTS = {
    AppType.CHAT: CHAT_SYSTEM_PROMPT,
    AppType.EMAIL: EMAIL_SYSTEM_PROMPT,
    AppType.CODE: CODE_SYSTEM_PROMPT,
    AppType.DOCUMENT: DOCUMENT_SYSTEM_PROMPT,
}

# ── Common words to exclude from proper noun extraction ──────────────

_COMMON_UPPER = frozenset({
    "I", "OK", "AM", "PM", "US", "TV", "IT", "ID",
    "The", "This", "That", "Here", "There", "Yes", "No",
    "New", "Open", "Save", "Close", "File", "Edit", "View",
    "Help", "Home", "Back", "Next", "Send", "Reply",
    "Delete", "Settings", "Search", "Menu", "Type",
    "Start", "Stop", "Cancel", "Apply", "Submit",
    "Log", "Sign", "Out", "In", "Up", "Down",
})

# ── App detection keywords ───────────────────────────────────────────

_CHAT_KEYWORDS = [
    "slack", "discord", "teams", "telegram", "whatsapp",
    "messenger", "signal", "imessage", "groupme",
]
_EMAIL_TITLE_KEYWORDS = [
    "outlook", "gmail", "mail", "thunderbird", "protonmail",
]
_EMAIL_OCR_KEYWORDS = ["subject:", "to:", "cc:", "bcc:", "from:"]
_CODE_KEYWORDS = [
    "visual studio", "vscode", "code -", "pycharm", "intellij",
    "vim", "neovim", "sublime", "atom", "cursor", "zed",
]
_DOC_KEYWORDS = [
    "word", "google docs", "notion", "obsidian", "notepad",
    "libreoffice", "pages",
]

# ── Whisper prompt prefixes ──────────────────────────────────────────

_CONTEXT_PREFIX = {
    AppType.CHAT: "A conversation mentioning",
    AppType.EMAIL: "An email discussion involving",
    AppType.CODE: "A technical discussion about",
    AppType.DOCUMENT: "A document mentioning",
    AppType.GENERAL: "A discussion mentioning",
}


class ScreenContextEngine:
    """Captures the active window via OCR and extracts context."""

    def __init__(self):
        self.logger = get_logger()

    def capture(self):
        """Run the full OCR pipeline. Returns ScreenContext or None on failure."""
        try:
            title, rect = self._get_foreground_window()
            if not rect or rect[2] <= 0 or rect[3] <= 0:
                self.logger.warning("OCR: invalid window rect, skipping")
                return None

            image = self._capture_window(rect)
            if image is None:
                return None

            raw_text = self._extract_text(image)
            app_type = self._detect_app_type(raw_text, title)
            proper_nouns = self._extract_proper_nouns(raw_text)

            self.logger.info(
                f"OCR: app={app_type.value}, nouns={len(proper_nouns)}, "
                f"text={len(raw_text)} chars, title='{title[:50]}'"
            )
            return ScreenContext(
                raw_text=raw_text,
                app_type=app_type,
                proper_nouns=proper_nouns,
                window_title=title,
            )
        except Exception as e:
            self.logger.warning(f"OCR capture failed: {e}")
            return None

    # ── Window capture ───────────────────────────────────────────────

    def _get_foreground_window(self):
        """Get the foreground window title and bounding rect."""
        user32 = ctypes.windll.user32

        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return "", (0, 0, 0, 0)

        # Get title
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value

        # Get rect
        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        x, y, w, h = rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top

        return title, (x, y, w, h)

    def _capture_window(self, rect):
        """Capture a screenshot of the given window region.

        Returns a tuple (rgba_bytes, width, height) for winocr, or None on failure.
        """
        try:
            import mss
            import numpy as np
            x, y, w, h = rect
            monitor = {"left": x, "top": y, "width": w, "height": h}
            with mss.mss() as sct:
                screenshot = sct.grab(monitor)
                # mss gives BGRA; winocr needs RGBA — swap B and R channels via numpy
                arr = np.frombuffer(screenshot.bgra, dtype=np.uint8).reshape(-1, 4).copy()
                arr[:, [0, 2]] = arr[:, [2, 0]]
                return (arr.tobytes(), screenshot.width, screenshot.height)
        except Exception as e:
            self.logger.warning(f"OCR: screenshot failed: {e}")
            return None

    # ── OCR ──────────────────────────────────────────────────────────

    def _extract_text(self, capture_data):
        """Run Windows native OCR on raw RGBA bytes."""
        try:
            import asyncio
            import winocr

            rgba_bytes, width, height = capture_data

            # winocr is async — run in a new event loop
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(
                    winocr.recognize_bytes(rgba_bytes, width, height, lang="en")
                )
            finally:
                loop.close()

            # Extract text from result (WinRT OcrResult uses attributes, not dicts)
            lines = []
            for line in result.lines:
                lines.append(line.text)
            return "\n".join(lines)
        except Exception as e:
            self.logger.warning(f"OCR: text extraction failed: {e}")
            return ""

    # ── App type detection ───────────────────────────────────────────

    def _detect_app_type(self, ocr_text, window_title):
        """Detect the app type from window title and OCR text."""
        title = window_title.lower()

        if any(k in title for k in _CHAT_KEYWORDS):
            return AppType.CHAT

        if any(k in title for k in _EMAIL_TITLE_KEYWORDS):
            return AppType.EMAIL
        if any(k in ocr_text.lower() for k in _EMAIL_OCR_KEYWORDS):
            return AppType.EMAIL

        if any(k in title for k in _CODE_KEYWORDS):
            return AppType.CODE

        if any(k in title for k in _DOC_KEYWORDS):
            return AppType.DOCUMENT

        return AppType.GENERAL

    # ── Proper noun extraction ───────────────────────────────────────

    def _extract_proper_nouns(self, ocr_text):
        """Extract likely proper nouns from OCR text."""
        words = ocr_text.split()
        proper_nouns = []
        seen = set()

        for word in words:
            clean = word.strip(".,!?:;\"'()[]{}")
            if not clean or len(clean) < 2:
                continue
            if clean[0].isupper() and clean not in _COMMON_UPPER:
                if not clean.isupper() or len(clean) <= 4:
                    lower = clean.lower()
                    if lower not in seen:
                        seen.add(lower)
                        proper_nouns.append(clean)

        return proper_nouns[:30]

    # ── Static helpers (used by TranscriptionWorker) ─────────────────

    @staticmethod
    def build_whisper_prompt(proper_nouns, app_type):
        """Build a natural-language initial_prompt for Whisper."""
        if not proper_nouns:
            return ""

        prefix = _CONTEXT_PREFIX.get(app_type, "A discussion mentioning")

        if len(proper_nouns) == 1:
            names = proper_nouns[0]
        elif len(proper_nouns) == 2:
            names = f"{proper_nouns[0]} and {proper_nouns[1]}"
        else:
            names = ", ".join(proper_nouns[:-1]) + f", and {proper_nouns[-1]}"

        prompt = f"{prefix} {names}."
        if len(prompt) > 800:
            prompt = prompt[:800]
        return prompt

    @staticmethod
    def build_system_prompt(app_type, proper_nouns):
        """Select the system prompt for the app type, with noun hints."""
        from core.post_processor import SYSTEM_PROMPT
        prompt = _APP_TYPE_PROMPTS.get(app_type, SYSTEM_PROMPT)

        if proper_nouns:
            names = ", ".join(proper_nouns[:15])
            prompt += (
                f"\n\nNames and terms visible on screen: {names}\n"
                "Use these exact spellings when they appear in the input."
            )
        return prompt

    @staticmethod
    def apply_chat_formatting(text):
        """Strip trailing period from chat messages."""
        if not text:
            return text
        if text.endswith('.') and not text.endswith('...'):
            text = text[:-1]
        return text

    @staticmethod
    def apply_email_structure(text, context):
        """Add greeting if recipient detected in OCR text."""
        if not text or len(text.split()) < 10:
            return text

        # Try to find recipient from "To:" field in OCR
        recipient = None
        for line in context.raw_text.split("\n"):
            stripped = line.strip()
            if stripped.lower().startswith("to:"):
                # Extract the name part (before any email address)
                name_part = stripped[3:].strip()
                # Remove email if present
                if "<" in name_part:
                    name_part = name_part[:name_part.index("<")].strip()
                if name_part and len(name_part) < 50:
                    recipient = name_part
                break

        if not recipient:
            return text

        greetings = ["hi ", "hey ", "hello ", "dear ", "good morning", "good afternoon"]
        if any(text.lower().startswith(g) for g in greetings):
            return text

        return f"Hi {recipient},\n\n{text}"
