"""
Passive self-learning engine for OCR context.
Builds per-app profiles from screen captures to improve transcription
accuracy over time. Learns vocabulary and communication style from
what's visible on screen — never stores raw text or conversations.
"""

import json
import re
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path

from utils.resource_path import get_app_data_path
from utils.logger import get_logger

# Known apps for window title normalization and web app detection.
# Maps lowercase name fragments to (app_key, display_name, app_type).
KNOWN_APPS = {
    "discord": ("discord", "Discord", "chat"),
    "slack": ("slack", "Slack", "chat"),
    "telegram": ("telegram", "Telegram", "chat"),
    "whatsapp": ("whatsapp", "WhatsApp", "chat"),
    "microsoft teams": ("teams", "Microsoft Teams", "chat"),
    "teams": ("teams", "Microsoft Teams", "chat"),
    "outlook": ("outlook", "Outlook", "email"),
    "gmail": ("gmail", "Gmail", "email"),
    "thunderbird": ("thunderbird", "Thunderbird", "email"),
    "visual studio code": ("visual_studio_code", "Visual Studio Code", "code"),
    "vs code": ("visual_studio_code", "Visual Studio Code", "code"),
    "vscode": ("visual_studio_code", "Visual Studio Code", "code"),
    "pycharm": ("pycharm", "PyCharm", "code"),
    "intellij": ("intellij", "IntelliJ IDEA", "code"),
    "sublime text": ("sublime_text", "Sublime Text", "code"),
    "notepad++": ("notepad_plus_plus", "Notepad++", "code"),
    "vim": ("vim", "Vim", "code"),
    "neovim": ("neovim", "Neovim", "code"),
    "word": ("word", "Microsoft Word", "document"),
    "microsoft word": ("word", "Microsoft Word", "document"),
    "google docs": ("google_docs", "Google Docs", "document"),
    "notion": ("notion", "Notion", "document"),
    "obsidian": ("obsidian", "Obsidian", "document"),
    "excel": ("excel", "Microsoft Excel", "document"),
    "microsoft excel": ("excel", "Microsoft Excel", "document"),
    "google sheets": ("google_sheets", "Google Sheets", "document"),
    "powerpoint": ("powerpoint", "Microsoft PowerPoint", "document"),
    "google slides": ("google_slides", "Google Slides", "document"),
    "notepad": ("notepad", "Notepad", "document"),
    "windows terminal": ("windows_terminal", "Windows Terminal", "terminal"),
    "command prompt": ("command_prompt", "Command Prompt", "terminal"),
    "powershell": ("powershell", "PowerShell", "terminal"),
    "git bash": ("git_bash", "Git Bash", "terminal"),
    "claude code": ("claude_code", "Claude Code", "terminal"),
    "cursor": ("cursor", "Cursor", "code"),
    "terminal": ("terminal", "Terminal", "terminal"),
    "warp": ("warp", "Warp", "terminal"),
    "iterm": ("iterm", "iTerm", "terminal"),
}

# Browser identifiers — used to detect web apps running inside browsers.
BROWSERS = {"google chrome", "chrome", "firefox", "mozilla firefox",
            "microsoft edge", "edge", "brave", "opera", "vivaldi", "safari"}

# Common abbreviations/slang for style analysis.
ABBREVIATIONS = {
    "lol", "lmao", "rofl", "brb", "afk", "gg", "wp", "imo", "imho",
    "tbh", "ngl", "smh", "fyi", "btw", "idk", "omg", "wtf", "ty",
    "thx", "np", "nvm", "rn", "fr", "istg", "wdym", "ikr", "nah",
    "yep", "yup", "k", "ok", "pls", "plz", "u", "ur", "r",
}

# Proper noun pattern — capitalized words that aren't sentence starters.
_PROPER_NOUN_RE = re.compile(r"(?<!\.\s)(?<!\A)\b([A-Z][a-z]{2,})\b")

# Limits
MAX_VOCABULARY_PER_APP = 100
MAX_PROFILES = 200
STALE_DAYS = 90
MIN_SAMPLES_FOR_STYLE = 3
EMA_ALPHA = 0.3  # Exponential moving average smoothing factor


@dataclass
class StyleMetrics:
    """Statistical style profile computed from OCR text."""
    avg_words_per_line: float = 0.0
    capitalization_ratio: float = 0.0
    punctuation_ratio: float = 0.0
    formality_score: float = 0.0
    abbreviation_count: int = 0
    sample_count: int = 0

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        if not data:
            return cls()
        return cls(
            avg_words_per_line=data.get("avg_words_per_line", 0.0),
            capitalization_ratio=data.get("capitalization_ratio", 0.0),
            punctuation_ratio=data.get("punctuation_ratio", 0.0),
            formality_score=data.get("formality_score", 0.0),
            abbreviation_count=int(data.get("abbreviation_count", 0)),
            sample_count=int(data.get("sample_count", 0)),
        )


@dataclass
class AppProfile:
    """Learned profile for a specific application."""
    app_key: str = ""
    display_name: str = ""
    app_type: str = "general"
    confidence: float = 0.0
    sessions: int = 0
    last_used: str = ""
    vocabulary: list = field(default_factory=list)
    vocabulary_frequency: dict = field(default_factory=dict)
    style_metrics: StyleMetrics = field(default_factory=StyleMetrics)

    def to_dict(self):
        d = asdict(self)
        d["style_metrics"] = self.style_metrics.to_dict()
        return d

    @classmethod
    def from_dict(cls, data):
        if not data:
            return cls()
        style = StyleMetrics.from_dict(data.get("style_metrics"))
        return cls(
            app_key=data.get("app_key", ""),
            display_name=data.get("display_name", ""),
            app_type=data.get("app_type", "general"),
            confidence=data.get("confidence", 0.0),
            sessions=int(data.get("sessions", 0)),
            last_used=data.get("last_used", ""),
            vocabulary=list(data.get("vocabulary", [])),
            vocabulary_frequency=dict(data.get("vocabulary_frequency", {})),
            style_metrics=style,
        )


class LearningEngine:
    """
    Passive learning engine that builds per-app profiles from OCR data.

    Observes screen content to learn:
    - App types and identifiers
    - Proper noun vocabulary for Whisper hints
    - Communication style metrics for adaptive formatting

    Thread-safe — all mutations go through a lock.
    Privacy-preserving — only stores identifiers, vocabulary, and statistics.
    """

    def __init__(self):
        self.logger = get_logger()
        self._lock = threading.Lock()
        self._profiles: dict[str, AppProfile] = {}
        self._storage_path = Path(get_app_data_path("learning")) / "app_profiles.json"
        self.load()
        self.logger.info("LearningEngine initialized (%d profiles loaded)", len(self._profiles))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def learn_from_context(self, window_title, ocr_text, detected_app_type=None):
        """
        Update profile with new OCR observation.

        Args:
            window_title: Current window title string.
            ocr_text: Raw OCR text extracted from the screen.
            detected_app_type: App type detected by OCR system (chat/email/code/document/general).
        """
        if not window_title:
            return

        app_key, display_name, fallback_type = self._normalize_app_key(window_title)
        app_type = detected_app_type or fallback_type

        with self._lock:
            profile = self._profiles.get(app_key)
            if profile is None:
                profile = AppProfile(app_key=app_key, display_name=display_name)
                self._profiles[app_key] = profile

            # Update app type with confidence
            if app_type and app_type != "general":
                if profile.app_type == app_type:
                    profile.confidence = min(1.0, profile.confidence + 0.05)
                elif profile.app_type == "general" or profile.confidence < 0.3:
                    profile.app_type = app_type
                    profile.confidence = 0.3

            profile.sessions += 1
            profile.last_used = datetime.now().isoformat()

            # Update display name if we got a better one from KNOWN_APPS
            if display_name and display_name != app_key:
                profile.display_name = display_name

            # Learn from OCR text
            if ocr_text and ocr_text.strip():
                self._update_vocabulary(profile, ocr_text)
                self._update_style_metrics(profile, ocr_text)

            # Enforce limits
            self._enforce_limits()

    def get_profile(self, window_title):
        """Get learned profile for an app, or None if unknown."""
        if not window_title:
            return None
        app_key, _, _ = self._normalize_app_key(window_title)
        with self._lock:
            return self._profiles.get(app_key)

    def get_vocabulary(self, window_title):
        """
        Get learned vocabulary terms for Whisper initial_prompt hints.

        Returns terms sorted by frequency (highest-frequency LAST for
        Whisper attention bias toward end tokens). Capped at 15 terms.
        """
        profile = self.get_profile(window_title)
        if not profile or not profile.vocabulary:
            return []
        # Sort ascending by frequency so highest-frequency terms are last
        freq = profile.vocabulary_frequency
        terms = sorted(profile.vocabulary, key=lambda t: freq.get(t.lower(), 0))
        return terms[-15:]  # Cap at 15 terms

    def get_style_hints(self, window_title):
        """Get style metrics dict if enough samples exist."""
        profile = self.get_profile(window_title)
        if not profile:
            return None
        if profile.style_metrics.sample_count < MIN_SAMPLES_FOR_STYLE:
            return None
        return profile.style_metrics.to_dict()

    def get_app_type(self, window_title):
        """Get remembered app type if confidence >= 0.5, else None."""
        profile = self.get_profile(window_title)
        if not profile:
            return None
        if profile.confidence >= 0.5:
            return profile.app_type
        return None

    def build_style_prompt_suffix(self, window_title):
        """
        Build a dynamic prompt suffix based on learned style.

        Returns a string like "Use casual style with minimal punctuation."
        or None if not enough data.
        """
        hints = self.get_style_hints(window_title)
        if not hints:
            return None

        parts = []
        formality = hints.get("formality_score", 0.5)
        punct = hints.get("punctuation_ratio", 0.5)
        cap = hints.get("capitalization_ratio", 0.5)

        # Formality
        if formality < 0.3:
            parts.append("Use casual, conversational style.")
        elif formality > 0.7:
            parts.append("Use formal, professional style.")

        # Punctuation
        if punct < 0.3:
            parts.append("Minimal punctuation.")
        elif punct > 0.7:
            parts.append("Use proper punctuation.")

        # Capitalization
        if cap < 0.3:
            parts.append("Lowercase is acceptable.")
        elif cap > 0.7:
            parts.append("Use standard capitalization.")

        if not parts:
            return None

        return " ".join(parts)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self):
        """Persist profiles to disk."""
        with self._lock:
            data = {
                "version": "1.0",
                "profiles": {
                    key: profile.to_dict()
                    for key, profile in self._profiles.items()
                },
            }
        try:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            self.logger.info("Learning profiles saved (%d profiles)", len(data["profiles"]))
        except Exception as e:
            self.logger.error("Failed to save learning profiles: %s", e)

    def load(self):
        """Load profiles from disk."""
        if not self._storage_path.exists():
            return
        try:
            with open(self._storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            profiles_data = data.get("profiles", {})
            with self._lock:
                self._profiles = {
                    key: AppProfile.from_dict(pdata)
                    for key, pdata in profiles_data.items()
                }
            self.logger.info("Loaded %d learning profiles", len(self._profiles))
        except Exception as e:
            self.logger.error("Failed to load learning profiles: %s", e)

    # ------------------------------------------------------------------
    # App key normalization
    # ------------------------------------------------------------------

    def _normalize_app_key(self, window_title):
        """
        Extract a stable app key from a volatile window title.

        Returns:
            (app_key, display_name, app_type) tuple.

        Examples:
            "Discord - #general - My Server" → ("discord", "Discord", "chat")
            "Inbox - user@email.com - Outlook" → ("outlook", "Outlook", "email")
            "Outlook - Google Chrome" → ("outlook", "Outlook", "email")  # web app!
            "settings.py - Resonance - Visual Studio Code" → ("visual_studio_code", "Visual Studio Code", "code")
        """
        if not window_title:
            return ("unknown", "Unknown", "general")

        title_lower = window_title.lower().strip()

        # Split title into segments (most apps use " - " as separator)
        segments = [s.strip() for s in window_title.split(" - ")]
        segments_lower = [s.lower() for s in segments]

        # Check if last segment is a browser — if so, look for web apps in other segments
        is_browser = len(segments) > 1 and any(
            b in segments_lower[-1] for b in BROWSERS
        )

        # Search segments for known apps (prefer later segments, which are usually the app name)
        for segment_lower in reversed(segments_lower):
            # Skip browser segment itself
            if is_browser and any(b in segment_lower for b in BROWSERS):
                continue
            # Check against known apps — try longest match first
            for app_name in sorted(KNOWN_APPS, key=len, reverse=True):
                if app_name in segment_lower:
                    app_key, display_name, app_type = KNOWN_APPS[app_name]
                    return (app_key, display_name, app_type)

        # Also check the full title for known apps (handles single-segment titles)
        for app_name in sorted(KNOWN_APPS, key=len, reverse=True):
            if app_name in title_lower:
                app_key, display_name, app_type = KNOWN_APPS[app_name]
                return (app_key, display_name, app_type)

        # No known app found — use the last non-browser segment as the app name
        if is_browser and len(segments) > 1:
            app_segment = segments[-2]
        elif segments:
            app_segment = segments[-1]
        else:
            app_segment = window_title

        # Clean and create a key from the segment
        app_key = re.sub(r"[^a-z0-9]+", "_", app_segment.lower()).strip("_")
        if not app_key:
            app_key = "unknown"

        display_name = app_segment.strip()
        return (app_key, display_name, "general")

    # ------------------------------------------------------------------
    # Vocabulary extraction
    # ------------------------------------------------------------------

    def _update_vocabulary(self, profile, ocr_text):
        """Extract proper nouns from OCR text and update vocabulary."""
        lines = ocr_text.strip().split("\n")
        candidates = set()

        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Find capitalized words that aren't at the start of a sentence
            words = line.split()
            for i, word in enumerate(words):
                # Skip first word of line (likely sentence start)
                if i == 0:
                    continue
                # Skip short words and all-caps (likely acronyms handled separately)
                clean = re.sub(r"[^a-zA-Z]", "", word)
                if len(clean) < 3:
                    continue
                if clean[0].isupper() and not clean.isupper():
                    candidates.add(clean)

        # Update frequency map
        for term in candidates:
            key = term.lower()
            profile.vocabulary_frequency[key] = profile.vocabulary_frequency.get(key, 0) + 1
            # Add to vocabulary list if not present (case-preserved)
            if not any(v.lower() == key for v in profile.vocabulary):
                profile.vocabulary.append(term)

        # Trim vocabulary to limit — keep highest frequency terms
        if len(profile.vocabulary) > MAX_VOCABULARY_PER_APP:
            freq = profile.vocabulary_frequency
            profile.vocabulary.sort(key=lambda t: freq.get(t.lower(), 0), reverse=True)
            removed = profile.vocabulary[MAX_VOCABULARY_PER_APP:]
            profile.vocabulary = profile.vocabulary[:MAX_VOCABULARY_PER_APP]
            # Clean up frequency map
            for term in removed:
                profile.vocabulary_frequency.pop(term.lower(), None)

    # ------------------------------------------------------------------
    # Style metrics
    # ------------------------------------------------------------------

    def _update_style_metrics(self, profile, ocr_text):
        """Compute style metrics from OCR text and merge via EMA."""
        lines = [l.strip() for l in ocr_text.strip().split("\n") if l.strip()]
        if not lines:
            return

        # Words per line
        word_counts = [len(l.split()) for l in lines]
        avg_words = sum(word_counts) / len(word_counts)

        # Capitalization ratio — fraction of lines starting with uppercase
        cap_lines = sum(1 for l in lines if l and l[0].isupper())
        cap_ratio = cap_lines / len(lines)

        # Punctuation ratio — fraction of lines ending with . ! ?
        punct_lines = sum(1 for l in lines if l and l[-1] in ".!?")
        punct_ratio = punct_lines / len(lines)

        # Abbreviation count — count slang terms in text
        words_lower = set(ocr_text.lower().split())
        abbrev_count = len(words_lower & ABBREVIATIONS)

        # Formality score — composite of other metrics
        formality = self._compute_formality(cap_ratio, punct_ratio, avg_words, abbrev_count)

        # Merge with existing via exponential moving average
        sm = profile.style_metrics
        if sm.sample_count == 0:
            sm.avg_words_per_line = avg_words
            sm.capitalization_ratio = cap_ratio
            sm.punctuation_ratio = punct_ratio
            sm.formality_score = formality
            sm.abbreviation_count = abbrev_count
        else:
            a = EMA_ALPHA
            sm.avg_words_per_line = a * avg_words + (1 - a) * sm.avg_words_per_line
            sm.capitalization_ratio = a * cap_ratio + (1 - a) * sm.capitalization_ratio
            sm.punctuation_ratio = a * punct_ratio + (1 - a) * sm.punctuation_ratio
            sm.formality_score = a * formality + (1 - a) * sm.formality_score
            sm.abbreviation_count = int(a * abbrev_count + (1 - a) * sm.abbreviation_count)

        sm.sample_count += 1

    def _compute_formality(self, cap_ratio, punct_ratio, avg_words, abbrev_count):
        """Compute a 0.0-1.0 formality score from style signals."""
        # Higher cap + punct + longer lines = more formal
        # More abbreviations = less formal
        score = (
            cap_ratio * 0.3
            + punct_ratio * 0.3
            + min(avg_words / 20.0, 1.0) * 0.25
            + max(0, 1.0 - abbrev_count / 5.0) * 0.15
        )
        return max(0.0, min(1.0, score))

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def _enforce_limits(self):
        """Enforce max profiles and clean stale entries. Must hold lock."""
        now = datetime.now()
        cutoff = now - timedelta(days=STALE_DAYS)

        # Remove stale profiles
        stale_keys = []
        for key, profile in self._profiles.items():
            if profile.last_used:
                try:
                    last = datetime.fromisoformat(profile.last_used)
                    if last < cutoff:
                        stale_keys.append(key)
                except (ValueError, TypeError):
                    pass

        for key in stale_keys:
            del self._profiles[key]
            self.logger.info("Removed stale profile: %s", key)

        # Enforce max profile count — remove least recently used
        if len(self._profiles) > MAX_PROFILES:
            sorted_profiles = sorted(
                self._profiles.items(),
                key=lambda x: x[1].last_used or "",
            )
            excess = len(self._profiles) - MAX_PROFILES
            for key, _ in sorted_profiles[:excess]:
                del self._profiles[key]
                self.logger.info("Removed excess profile: %s", key)
