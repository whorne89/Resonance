"""
Text cleanup applied between Whisper transcription and post-processing.

Two cleaners:
1. Comma-spam removal — Whisper sometimes inserts commas between every word
   when the speaker pauses. Strips excessive commas so the post-processor
   (or raw output) isn't polluted.
2. Spoken punctuation — converts spoken symbol names to actual characters
   (e.g., "slash" -> "/") for dictating commands, URLs, and code.
"""

import re


# Spoken punctuation -> symbol mappings.
# Multi-word phrases listed first — patterns are sorted longest-first
# at compile time so "open parenthesis" matches before "open paren".
SPOKEN_PUNCTUATION = [
    # Multi-word phrases
    ("forward slash", "/"),
    ("back slash", "\\"),
    ("open parenthesis", "("),
    ("close parenthesis", ")"),
    ("left parenthesis", "("),
    ("right parenthesis", ")"),
    ("open paren", "("),
    ("close paren", ")"),
    ("left paren", "("),
    ("right paren", ")"),
    ("open bracket", "["),
    ("close bracket", "]"),
    ("left bracket", "["),
    ("right bracket", "]"),
    ("open curly brace", "{"),
    ("close curly brace", "}"),
    ("left curly brace", "{"),
    ("right curly brace", "}"),
    ("open brace", "{"),
    ("close brace", "}"),
    ("left brace", "{"),
    ("right brace", "}"),
    ("exclamation point", "!"),
    ("exclamation mark", "!"),
    ("question mark", "?"),
    ("at sign", "@"),
    ("hash sign", "#"),
    ("dollar sign", "$"),
    ("percent sign", "%"),
    ("plus sign", "+"),
    ("equals sign", "="),
    ("new line", "\n"),
    ("new paragraph", "\n\n"),
    # Single-word entries
    ("backslash", "\\"),
    ("slash", "/"),
    ("colon", ":"),
    ("semicolon", ";"),
    ("underscore", "_"),
    ("tilde", "~"),
    ("pipe", "|"),
    ("ampersand", "&"),
    ("asterisk", "*"),
    ("hashtag", "#"),
    ("hyphen", "-"),
    ("dash", "-"),
    ("dot", "."),
]

# Pre-compile patterns sorted longest-first so multi-word phrases
# are matched before their single-word substrings.
_SPOKEN_PATTERNS = []
for _spoken, _symbol in sorted(SPOKEN_PUNCTUATION, key=lambda x: len(x[0]), reverse=True):
    _pat = re.compile(r'\b' + re.escape(_spoken) + r'\b', re.IGNORECASE)
    _SPOKEN_PATTERNS.append((_pat, _symbol))


def clean_comma_spam(text):
    """Remove excessive commas from Whisper output.

    Whisper sometimes inserts commas between most or every word when the
    speaker pauses between words, producing text like "Can, We, Fix, That"
    instead of "Can we fix that". This typically happens with emphatic or
    deliberately paced speech.

    Returns cleaned text with commas stripped if more than 50% of word
    boundaries had commas (indicating spam, not legitimate punctuation).
    """
    if not text:
        return text

    comma_count = text.count(',')
    words = text.replace(',', '').split()

    if len(words) <= 3:
        return text

    # If more than 50% of word gaps have commas, it's spam
    if comma_count > len(words) * 0.5:
        cleaned = text.replace(',', '')
        cleaned = ' '.join(cleaned.split())
        return cleaned

    return text


def replace_spoken_punctuation(text):
    """Convert spoken symbol names to actual characters.

    Handles dictation of special characters: "slash" -> "/",
    "at sign" -> "@", "open paren" -> "(", etc. Uses whole-word
    matching to minimize false positives.

    Does NOT handle "period", "comma", or "dot" — Whisper already
    converts those natively in most contexts.
    """
    if not text:
        return text

    for pattern, symbol in _SPOKEN_PATTERNS:
        text = pattern.sub(lambda m: symbol, text)

    # Collapse spaces around symbols so "/ resume" → "/resume",
    # "user @ gmail" → "user@gmail", "( x )" → "(x)", etc.
    # Prefix symbols: remove trailing space when followed by a word char
    text = re.sub(r'([/\\@#$~.\-]) (?=\w)', r'\1', text)
    # Attach to previous word: opening brackets and @
    text = re.sub(r'(?<=\w) (?=[(\[{@])', '', text)
    text = re.sub(r'([(\[{]) (?=\S)', r'\1', text)
    # Closing brackets / terminal punctuation: remove leading space
    text = re.sub(r'(?<=\S) ([)\]};:!?.])', r'\1', text)
    # Collapse runs of symbols with spaces between them (e.g., "/ /" → "//")
    text = re.sub(r'([/\\:~.]) (?=[/\\:~.])', r'\1', text)

    return text
