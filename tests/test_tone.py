"""Noah must sound like a warm person: feelings come through words, never emoji, and the fixed replies must not read like a script."""

import ast
import json
import re
from pathlib import Path

import pytest

from noah import brain, knowledge

ROOT = Path(__file__).resolve().parent.parent
SOURCES = sorted((ROOT / "noah").rglob("*.py"))
DATA_FILES = sorted((ROOT / "data").glob("*.json"))

ROBOTIC = [
    "i would be happy to assist", "please be advised", "as per our records", "i apologize for the inconvenience",
    "is there anything else i can help you with", "knowledge system", "matching command", "invalid input", "kindly note",
    "do the needful", "we regret to inform",
]


def is_emoji(ch):
    o = ord(ch)
    return o >= 0x1F000 or 0x2600 <= o <= 0x27BF or o in (0x2B50, 0x2B55, 0xFE0F, 0x200D)


def string_literals(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.value


def test_no_emoji_anywhere_in_what_noah_can_say():
    offenders = []
    for path in SOURCES:
        for text in string_literals(path):
            bad = [c for c in text if is_emoji(c)]
            if bad:
                offenders.append((path.name, text[:50]))
    for path in DATA_FILES:
        text = path.read_text(encoding="utf-8")
        if any(is_emoji(c) for c in text):
            offenders.append((path.name, "data file"))
    assert not offenders, offenders


def test_no_robotic_phrases_in_any_fixed_reply_or_prompt():
    found = []
    for path in SOURCES:
        for text in string_literals(path):
            low = text.lower()
            # the prompt lists these phrases only to forbid them; everything else must be free of them
            if "avoid stiff or corporate phrases" in low or "avoid stiff phrases" in low:
                continue
            for phrase in ROBOTIC:
                if phrase in low:
                    found.append((path.name, phrase))
    assert not found, found


# ---- the personality prompt -------------------------------------------------------------------------
def test_prompt_asks_for_a_warm_human_voice_without_emoji_and_stays_honest_about_being_an_assistant():
    p = brain.IDENTITY
    for needle in ("<personality>", "<examples>", "warm", "contractions", "never through emoji", "friend at the front desk",
                   "how the person seems to feel", "You are an assistant, not a human", "Never claim to be a person"):
        assert needle in p, needle
    # the identity facts survive the rewrite exactly
    for needle in ("Your name is Noah", "created by CogniAI Studios", "Rexy-1", "Abraham Shaun Sunil",
                   "NOT created by Anthropic, OpenAI, Google, Meta", "Never name any underlying model or vendor"):
        assert needle in p, needle


def test_prompt_keeps_every_hard_rule_and_marker():
    p = brain.IDENTITY
    for needle in ("Never invent information", "All fees are annual", "no monthly fee plan", "Never mix PU", "NOT an ICSE or CBSE school",
                   "[[UNKNOWN]]", "[[CRISIS]]", "[[OPEN:advisor]]", "[[OPEN:compare]]", "open to students of all religions"):
        assert needle in p, needle


def test_prompt_examples_use_the_real_fee_and_contain_no_emoji():
    fee = knowledge.DATA["fees"]["PCMB"]
    assert f"₹{fee:,}" in brain.IDENTITY                      # an example can never drift from the real fee
    example_block = brain.IDENTITY[brain.IDENTITY.index("<examples>"):]
    assert not any(is_emoji(c) for c in example_block)
    assert example_block.count("User:") == 5 and example_block.count("Noah:") == 5   # a few varied examples, not a wall of them


def test_prompt_stays_lean():
    assert len(brain.IDENTITY) < 9000


def test_language_rule_asks_for_natural_spoken_style():
    rule = brain.LANG_RULE.format(name="Hindi")
    assert "Hindi" in rule and "spoken" in rule and "not stiff" in rule


def test_gemini_gets_the_personality_and_qwen_gets_a_short_one(fake):
    brain.respond(brain.Ctx(text="tell me about the campus library", sid="sess-tone-1"))
    system = fake.gemini_calls[0]["body"]["systemInstruction"]["parts"][0]["text"]
    assert "<personality>" in system and "FACTS ABOUT THE COLLEGE" in system
    fake.gemini_mode = "500"
    brain.respond(brain.Ctx(text="and what about the lab timings", sid="sess-tone-2"))
    qwen_system = fake.llama_calls[0]["messages"][0]["content"]
    assert "warm, kind friend" in qwen_system and "Never use emoji" in qwen_system and "FACTS:" in qwen_system
    assert "<personality>" not in qwen_system and len(qwen_system) < 6000


def test_study_helper_is_an_encouraging_buddy():
    from noah.features import study
    t = study.SYSTEM_TUTOR
    assert "study helper" in t and "encouraging" in t and "never emoji" in t and "fixable" in t


# ---- what visitors actually read when no model is involved -------------------------------------------------
def ask(text, sid):
    return brain.respond(brain.Ctx(text=text, sid=sid))


@pytest.mark.parametrize("text,must_contain", [
    ("what is the fee for pcmb", ["80,000", "annual", "not monthly"]),
    ("who is the principal", ["Our Principal is"]),
    ("is there a hostel", ["wish I had better news", "hostel"]),
    ("tell me about the icse board", ["pointed the right way", "sister schools"]),
    ("who is the best actor", ["Ha,", "Is there something about the college I can help you with?"]),
    ("which stream should i choose", ["I'd love to help"]),
    ("i want to visit the campus", ["we'd love to see you"]),
    ("what documents are needed", ["Let me save you a trip"]),
    ("open ibdp faqs", ["Sure, opening"]),
])
def test_fixed_replies_sound_like_a_person(fake, text, must_contain):
    reply = ask(text, "sess-tone-" + str(abs(hash(text)) % 10000))
    for needle in must_contain:
        assert needle in reply.answer, (text, reply.answer)
    assert not any(is_emoji(c) for c in reply.answer)
    assert not any(p in reply.answer.lower() for p in ROBOTIC)


def test_apology_when_nothing_is_available_is_kind_and_still_gives_the_office_number(fake):
    fake.gemini_mode = fake.llama_mode = "500"
    reply = ask("tell me about lab facilities", "sess-tone-down")
    assert reply.answer.startswith("I'm so sorry") and "4012 9292" in reply.answer and "try again" in reply.answer


def test_greetings_are_friendly_on_every_page():
    for url in ("https://x/", "https://x/about-us-ibdp.php", "https://x/contact-us-pu.php", "https://x/faqs-pu.php", "https://x/student-life.php"):
        greeting = brain.page_context(url)["greeting"]
        assert "?" in greeting or "!" in greeting
        assert not any(is_emoji(c) for c in greeting)
    assert brain.page_context("https://x/")["greeting"].startswith("Hi there, I'm Noah!")


def test_widget_greeting_and_error_text_are_friendly():
    src = (ROOT / "static" / "widget.js").read_text(encoding="utf-8")
    assert "Hi there, I" in src and "happy to help" in src
    assert "I can" in src and "reach the server right now" in src
    assert "Could not reach the server" not in src
    assert src.isascii()
