"""The read-aloud voice must be a woman's voice whenever the device has one."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

SRC = (Path(__file__).resolve().parent.parent / "static" / "widget.js").read_text(encoding="utf-8")
START = SRC.index("var VOICE = {")
END = SRC.index("/* VOICE-END */")
VOICE_JS = SRC[START:END]

WINDOWS = [("Microsoft David - English (United States)", "en-US"), ("Microsoft Zira - English (United States)", "en-US"),
           ("Microsoft Prabhat - English (India)", "en-IN"), ("Microsoft Neerja Online (Natural) - English (India)", "en-IN"),
           ("Microsoft Madhur - Hindi (India)", "hi-IN"), ("Microsoft Swara - Hindi (India)", "hi-IN"),
           ("Microsoft Gagan - Kannada (India)", "kn-IN"), ("Microsoft Sapna - Kannada (India)", "kn-IN"),
           ("Microsoft Valluvar - Tamil (India)", "ta-IN"), ("Microsoft Pallavi - Tamil (India)", "ta-IN"),
           ("Microsoft Midhun - Malayalam (India)", "ml-IN"), ("Microsoft Sobhana - Malayalam (India)", "ml-IN"),
           ("Microsoft Mohan - Telugu (India)", "te-IN"), ("Microsoft Shruti - Telugu (India)", "te-IN")]
APPLE = [("Daniel", "en-GB"), ("Rishi", "en-IN"), ("Samantha", "en-US"), ("Veena", "en-IN"), ("Lekha", "hi-IN")]
GOOGLE = [("Google UK English Male", "en-GB"), ("Google UK English Female", "en-GB"), ("Google US English", "en-US"), ("Google हिन्दी", "hi-IN")]


def pick(voices, lang, speech):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    script = (VOICE_JS + "; const v = JSON.parse(process.argv[1]).map(([name, lang]) => ({name, lang}));"
              "const r = VOICE.pick(v, process.argv[2], process.argv[3]);"
              "console.log(JSON.stringify({name: r.voice && r.voice.name, confirmed: r.confirmed}));")
    out = subprocess.run([node, "-e", script, json.dumps(voices), lang, speech], capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(out.stdout)


@pytest.mark.parametrize("lang,speech,expected", [
    ("en", "en-IN", "Neerja"), ("hi", "hi-IN", "Swara"), ("kn", "kn-IN", "Sapna"),
    ("ta", "ta-IN", "Pallavi"), ("ml", "ml-IN", "Sobhana"), ("te", "te-IN", "Shruti")])
def test_windows_voices_pick_the_woman_in_every_language(lang, speech, expected):
    result = pick(WINDOWS, lang, speech)
    assert expected in result["name"] and result["confirmed"]


def test_apple_voices():
    assert pick(APPLE, "en", "en-IN")["name"] == "Veena"
    assert pick(APPLE, "hi", "hi-IN")["name"] == "Lekha"


def test_google_voices_never_pick_the_male_one():
    for lang, speech in (("en", "en-IN"), ("hi", "hi-IN")):
        result = pick(GOOGLE, lang, speech)
        assert "Male" not in result["name"] and result["confirmed"]


def test_male_only_device_is_flagged_so_the_pitch_gets_raised():
    result = pick([("Microsoft Madhur - Hindi (India)", "hi-IN")], "hi", "hi-IN")
    assert result == {"name": "Microsoft Madhur - Hindi (India)", "confirmed": False}


def test_no_voices_is_safe():
    assert pick([], "en", "en-IN") == {"name": None, "confirmed": False}


def test_pitch_is_raised_when_no_female_voice_is_confirmed():
    assert "pick.confirmed ? 1.05 : 1.3" in SRC
