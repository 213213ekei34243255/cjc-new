"""Feature 13 - wellness check-in and the always-on crisis safety net.

Design rules:
* Never diagnose, never give medical advice, never replace the counsellor.
* The check-in is answered from fixed, reviewable text - not generated - so nobody can be harmed by a
  model's improvisation. The counselling team should read data/wellness.json and this file before launch.
* Wellness chats and check-ins are never written to the chat log (see brain.py `private`).
* The crisis check runs on EVERY message, in every mode, before anything else.
"""

import json
import re

from .. import config

_cache = None


def data():
    global _cache
    if _cache is None:
        _cache = json.loads((config.DATA_DIR / "wellness.json").read_text(encoding="utf-8"))
    return _cache


_CRISIS = re.compile(
    r"(kill(ing)?\s+myself|end(ing)?\s+my\s+life|want(\s+to|ed\s+to)?\s+die|wanna\s+die|suicid|end\s+it\s+all|"
    r"hurt(ing)?\s+myself|harm(ing)?\s+myself|self[\s-]?harm|cut(ting)?\s+myself|no\s+reason\s+to\s+live|"
    r"(don'?t|do\s+not|dont)\s+want\s+to\s+(live|be\s+alive|exist)|better\s+off\s+dead|can'?t\s+go\s+on|"
    r"take\s+my\s+own\s+life|"
    # Hindi / Hinglish
    r"khudkushi|aatmahatya|marna\s+chahta|mar\s+jana\s+chahta|jeena\s+nahi|jina\s+nahi|"
    r"आत्महत्या|खुदकुशी|मरना\s+चाह|जीना\s+नहीं|"
    # the word for "suicide" in Kannada, Tamil, Telugu, Malayalam
    r"ಆತ್ಮಹತ್ಯೆ|தற்கொலை|ఆత్మహత్య|ആത്മഹത്യ)",
    re.IGNORECASE,
)

# Gemini is told to answer with this marker when it senses danger in any language the rules miss.
MODEL_CRISIS_MARKER = "[[CRISIS]]"


def is_crisis(text):
    return bool(_CRISIS.search(text or ""))


def crisis_payload():
    d = data()
    return {
        "answer": ("I'm really glad you told me. You matter, and you do not have to carry this alone. "
                   "Please talk to someone right now - the free helpline below is open all day and night. "
                   "If you are in immediate danger, call 112 or go to the nearest hospital, and tell an adult you trust. "
                   + d["college_line"]),
        "helplines": d["helplines"],
        "college_line": d["college_line"],
    }


_TIPS = {
    "Exams and marks": "Break revision into 25-minute blocks with 5-minute rests, and ask your subject teacher about the one topic that worries you most. One exam does not decide your future.",
    "Family": "Choose one trusted adult and tell them one specific thing that is hard. A counsellor can help you plan that conversation.",
    "Friends or relationships": "Strong feelings about friends are normal at this age. Write down what happened and what you wish had happened - it helps to say it out loud to someone you trust.",
    "Sleep and energy": "Try a fixed sleep time, no screens for 30 minutes before bed, and water and a short walk in daylight. If tiredness continues for weeks, mention it to a doctor or counsellor.",
    "Future and career": "You do not have to decide everything today. The Careers tool shows where each stream can lead, and a counsellor can talk through options with you.",
    "Feeling alone": "Reaching out is the hardest step and you just took it. Message or sit with one person today, or join a club - shared activities make it easier to connect.",
    "Something else": "Whatever it is, it is fine to want support. A counsellor will listen without judging.",
}


def checkin(mood, concerns):
    try:
        mood = int(mood)
    except (TypeError, ValueError):
        mood = 3
    mood = max(1, min(5, mood))
    valid = set(data()["concerns"])
    concerns = [c for c in (concerns or []) if c in valid][:3]
    if mood <= 2:
        headline = "That sounds heavy"
        message = ("Thank you for being honest about how you feel. Low days are real, and they are not a sign that something is "
                   "wrong with you. You do not have to handle this alone.")
    elif mood == 3:
        headline = "Okay is allowed"
        message = "Okay days count too. A small reset can help - try the breathing exercise below."
    else:
        headline = "Good to hear"
        message = "Glad things feel good. Small habits like sleep, movement and talking to friends keep it that way."
    return {
        "headline": headline,
        "message": message,
        "tips": [_TIPS[c] for c in concerns],
        "suggest_counsellor": mood <= 3 or bool(concerns),
        "show_helplines": mood <= 2 or "Feeling alone" in concerns,
        "helplines": data()["helplines"],
        "college_line": data()["college_line"],
        "grounding": data()["grounding"],
    }
