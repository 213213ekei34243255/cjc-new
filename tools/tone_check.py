"""Hear how Noah really sounds, using your real Gemini key (the one in .env).

    python tools/tone_check.py

It asks a dozen typical questions, prints Noah's replies and flags anything that breaks the voice rules
(emoji, stiff phrases, very long answers). It uses a throw-away database, so nothing it does shows up in
the staff panel, and it never sends an email. If a reply sounds wrong, edit the <personality> and
<examples> blocks of IDENTITY in noah/brain.py, then run this again.
"""

import os
import sys
import tempfile
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["NOAH_DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="noah-tone-"), "tone.db")
os.environ["SMTP_HOST"] = ""            # never email anyone from a tone test

from noah import brain, config, llm  # noqa: E402

QUESTIONS = [
    ("hi", "en"),
    ("how much is PCMB", "en"),
    ("my daughter is really nervous about getting a seat, what should we do", "en"),
    ("I got only 62 percent in class 10, is that bad", "en"),
    ("do you have a swimming pool", "en"),
    ("who will win the world cup", "en"),
    ("are you a real person?", "en"),
    ("thank you so much, that helped!", "en"),
    ("tell me about the library timings", "en"),
    ("hello mujhe madad chahiye", "hi"),
    ("ನಮಸ್ಕಾರ, ಪ್ರವೇಶ ಹೇಗೆ ಮಾಡಬೇಕು?", "kn"),
    ("what's the difference between PU and IBDP", "en"),
]
STIFF = ["i would be happy to assist", "please be advised", "as per our records", "i apologize for the inconvenience",
         "is there anything else i can help you with", "as an ai"]


def is_emoji(ch):
    o = ord(ch)
    return o >= 0x1F000 or 0x2600 <= o <= 0x27BF or o in (0x2B50, 0x2B55, 0xFE0F, 0x200D)


def main():
    if not llm.gemini_configured():
        print("GEMINI_API_KEY is not set (put it in .env), so this would only test the Qwen backup.")
        if not llm.qwen_available():
            sys.exit("No model is reachable. Set the key and try again.")
    print(f"Model: {config.GEMINI_MODEL}\n")
    problems = 0
    for i, (text, lang) in enumerate(QUESTIONS, 1):
        reply = brain.respond(brain.Ctx(text=text, sid=f"tone-check-{i:02d}", lang_pref=lang))
        flags = []
        if any(is_emoji(c) for c in reply.answer):
            flags.append("EMOJI")
        if any(p in reply.answer.lower() for p in STIFF):
            flags.append("STIFF PHRASE")
        if len(reply.answer.split()) > 130:
            flags.append("TOO LONG")
        if flags:
            problems += 1
        print(f"[{i:02d}] You : {text}")
        print(textwrap.fill(f"Noah ({reply.engine}): {reply.answer}", 100, initial_indent="     ", subsequent_indent="     "))
        if flags:
            print("     >>> " + ", ".join(flags))
        print()
    print("All replies passed the voice checks." if not problems else f"{problems} reply(ies) broke the voice rules.")
    print("Now read them out loud: do they sound like a kind person at the front desk? If not, tune IDENTITY in noah/brain.py.")


if __name__ == "__main__":
    main()
