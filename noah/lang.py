"""Language handling: which languages Noah speaks and detecting them from the script typed."""

import re

LANGS = {
    "en": {"name": "English", "native": "English", "speech": "en-IN"},
    "kn": {"name": "Kannada", "native": "ಕನ್ನಡ", "speech": "kn-IN"},
    "hi": {"name": "Hindi", "native": "हिन्दी", "speech": "hi-IN"},
    "ta": {"name": "Tamil", "native": "தமிழ்", "speech": "ta-IN"},
    "ml": {"name": "Malayalam", "native": "മലയാളം", "speech": "ml-IN"},
    "te": {"name": "Telugu", "native": "తెలుగు", "speech": "te-IN"},
}

_SCRIPTS = [
    ("kn", re.compile(r"[ಀ-೿]")),
    ("te", re.compile(r"[ఀ-౿]")),
    ("ta", re.compile(r"[஀-௿]")),
    ("ml", re.compile(r"[ഀ-ൿ]")),
    ("hi", re.compile(r"[ऀ-ॿ]")),
]


def detect_script(text):
    """Return the language code of the Indic script that dominates `text`, or None for Latin/other."""
    best, best_count = None, 0
    for code, pattern in _SCRIPTS:
        count = len(pattern.findall(text or ""))
        if count > best_count:
            best, best_count = code, count
    return best if best_count >= 2 else None


def resolve_lang(text, preferred):
    """Script beats the widget's selector; the selector beats the default (so Hinglish typed in
    Latin letters keeps the language the visitor picked)."""
    found = detect_script(text)
    if found:
        return found
    return preferred if preferred in LANGS else "en"


def lang_name(code):
    return LANGS.get(code, LANGS["en"])["name"]
