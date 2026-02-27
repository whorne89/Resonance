"""
Dictionary processing for post-transcription word replacement.

Provides exact and fuzzy matching against a user-defined dictionary
to correct common Whisper misrecognitions.
"""

import re
from difflib import SequenceMatcher


class DictionaryProcessor:
    """Applies custom dictionary replacements to transcribed text."""

    def __init__(self, config, logger):
        self.config = config
        self.logger = logger

    def apply(self, text):
        """
        Apply custom dictionary replacements to transcribed text.

        Two-phase approach:
        1. Exact matching — replaces known wrong variations case-insensitively
        2. Fuzzy matching — catches unknown variations by comparing
           sliding n-gram windows against dictionary words using
           normalized character similarity

        Args:
            text: Raw transcribed text

        Returns:
            Text with dictionary replacements applied
        """
        if not self.config.get_dictionary_enabled():
            return text

        replacements = self.config.get_dictionary_replacements()
        if not replacements:
            return text

        # Phase 1: Exact matching (known variations)
        for correct_word, wrong_variations in replacements.items():
            if not isinstance(wrong_variations, list):
                continue
            for wrong in wrong_variations:
                pattern = re.compile(re.escape(wrong), re.IGNORECASE)
                text = pattern.sub(correct_word, text)

        # Phase 2: Fuzzy matching (unknown variations)
        if self.config.get_dictionary_fuzzy_enabled():
            text = self._apply_fuzzy(text, replacements)

        return text

    def _apply_fuzzy(self, text, replacements):
        """
        Fuzzy matching pass for dictionary replacements.

        Scans the transcription using sliding windows of 1-4 words.
        For each window, normalizes both the window text and the
        dictionary word (lowercase, strip spaces/punctuation), then
        compares similarity. If a window is close enough to a
        dictionary word, it gets replaced.

        This catches cases where Whisper splits or re-spells a word
        differently in sentence context vs. isolation:
          "Kubernetes" -> might be heard as "Cooper Netties", "Kuber Netis", etc.
        """
        threshold = self.config.get_dictionary_fuzzy_threshold()
        words = text.split()

        if not words:
            return text

        # Build targets: (correct_word, normalized_form)
        targets = []
        for correct_word in replacements:
            norm = re.sub(r'[^a-z0-9]', '', correct_word.lower())
            if len(norm) >= 3:  # Skip very short words to avoid false positives
                targets.append((correct_word, norm))

        if not targets:
            return text

        result = []
        i = 0

        while i < len(words):
            best_match = None
            best_ratio = threshold
            best_window = 0

            for correct_word, norm_correct in targets:
                # Skip if this word was already the correct word (from phase 1)
                if i < len(words) and words[i].lower() == correct_word.lower():
                    continue

                # Max window size based on correct word length
                # "Kubernetes" (10 chars) -> up to 4 words ("Cooper Netties")
                max_win = min(4, max(2, len(norm_correct) // 3 + 1))

                for ws in range(1, min(max_win + 1, len(words) - i + 1)):
                    window_text = ' '.join(words[i:i + ws])
                    norm_window = re.sub(r'[^a-z0-9]', '', window_text.lower())

                    if not norm_window:
                        continue

                    # Length ratio check — normalized lengths should be similar
                    len_ratio = min(len(norm_correct), len(norm_window)) / max(len(norm_correct), len(norm_window))
                    if len_ratio < 0.6:
                        continue

                    ratio = SequenceMatcher(None, norm_correct, norm_window).ratio()
                    if ratio > best_ratio:
                        best_match = correct_word
                        best_ratio = ratio
                        best_window = ws

            if best_match and best_window > 0:
                # Preserve trailing punctuation from the last word in the window
                last_word = words[i + best_window - 1]
                trailing = ''
                stripped = last_word
                while stripped and not stripped[-1].isalnum():
                    trailing = stripped[-1] + trailing
                    stripped = stripped[:-1]

                result.append(best_match + trailing)
                self.logger.info(
                    f"Fuzzy match: '{' '.join(words[i:i + best_window])}' -> "
                    f"'{best_match}' (similarity: {best_ratio:.2f})"
                )
                i += best_window
            else:
                result.append(words[i])
                i += 1

        return ' '.join(result)
