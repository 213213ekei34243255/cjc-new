"""Every language must arrive intact: the real services send raw UTF-8 and an SSE content type with no charset,
and `requests` then assumes Latin-1 (that is what turned Hindi into 'à¤¨à¤®...'). The fakes now behave like the real services."""

import json

import pytest

from noah import brain, config, llm
from noah.lang import LANGS

NATIVE = {
    "hi": "नमस्ते! मैं नोआ हूँ। PCMB की फीस ₹80,000 प्रति वर्ष है।",
    "kn": "ನಮಸ್ಕಾರ! ನಾನು ನೋಆ. PCMB ಶುಲ್ಕ ವರ್ಷಕ್ಕೆ ₹80,000 ಆಗಿದೆ.",
    "ta": "வணக்கம்! நான் நோவா. PCMB கட்டணம் ஆண்டுக்கு ₹80,000 ஆகும்.",
    "ml": "നമസ്കാരം! ഞാൻ നോവ. PCMB ഫീസ് വർഷത്തിൽ ₹80,000 ആണ്.",
    "te": "నమస్కారం! నేను నోవా. PCMB ఫీజు సంవత్సరానికి ₹80,000.",
    "en": "Hello! I am Noah. The PCMB fee is ₹80,000 per year.",
}
MOJIBAKE = ("Ã", "à¤", "à²", "à®", "à´", "à°", "â‚¹", "â\x82¹")


def assert_clean(text):
    assert not any(bad in text for bad in MOJIBAKE), f"garbled text: {text!r}"


def ask(text, lang, sid):
    return brain.respond(brain.Ctx(text=text, sid=sid, lang_pref=lang))


def test_all_six_languages_are_configured():
    assert set(LANGS) == set(NATIVE)


@pytest.mark.parametrize("lang", sorted(NATIVE))
def test_streamed_gemini_text_keeps_every_script_and_the_rupee_sign(fake, lang):
    system = f"Reply in {LANGS[lang]['name']}."
    events = list(llm.generate_stream(system, [{"role": "user", "content": "INDICTEST"}]))
    text = "".join(p for k, p in events if k == "delta")
    assert text == NATIVE[lang]
    assert_clean(text)


@pytest.mark.parametrize("lang", sorted(NATIVE))
def test_non_streamed_gemini_text_is_intact(fake, lang):
    res = llm.generate(f"Reply in {LANGS[lang]['name']}.", [{"role": "user", "content": "INDICTEST"}])
    assert res.text == NATIVE[lang]


@pytest.mark.parametrize("lang", sorted(NATIVE))
def test_streamed_qwen_backup_text_is_intact(fake, lang):
    fake.gemini_mode = "500"
    events = list(llm.generate_stream("big", [{"role": "user", "content": "INDICTEST"}],
                                      qwen_system=f"Reply in {LANGS[lang]['name']}.", qwen_messages=[{"role": "user", "content": "INDICTEST"}]))
    assert events[-1][1]["engine"] == "qwen"
    assert "".join(p for k, p in events if k == "delta") == NATIVE[lang]


@pytest.mark.parametrize("lang", sorted(NATIVE))
def test_a_full_chat_reply_in_each_language_is_intact_in_both_endpoints(fake, client, lang):
    reply = ask("INDICTEST hello one", lang, "sess-lang-" + lang)
    assert reply.answer == NATIVE[lang]
    assert_clean(reply.answer)
    streamed = client.post("/predict/stream", json={"message": "INDICTEST hello two", "session_id": "sess-lang-s-" + lang, "lang": lang})
    events = [json.loads(line[6:]) for line in streamed.get_data(as_text=True).split("\n\n") if line.startswith("data: ")]
    assert events[-1]["reply"]["answer"] == NATIVE[lang]
    assert "".join(e["text"] for e in events if e["type"] == "delta") == NATIVE[lang]
    plain = client.post("/predict", json={"message": "INDICTEST hello three", "session_id": "sess-lang-p-" + lang, "lang": lang}).json
    assert plain["answer"] == NATIVE[lang]


@pytest.mark.parametrize("lang", sorted(NATIVE))
def test_the_chat_log_stores_each_language_without_damage(fake, fresh, lang):
    ask("INDICTEST hello", lang, "sess-log-" + lang)
    row = fresh._connect().execute("SELECT text FROM messages WHERE role='bot'").fetchone()
    assert row["text"] == NATIVE[lang]


def test_script_detection_picks_the_right_language_for_typed_text():
    from noah.lang import detect_script
    assert [detect_script(NATIVE[c]) for c in ("hi", "kn", "ta", "ml", "te")] == ["hi", "kn", "ta", "ml", "te"]
    assert detect_script(NATIVE["en"]) is None


def test_widget_file_is_pure_ascii_so_no_encoding_setting_can_garble_it():
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent / "static" / "widget.js").read_text(encoding="utf-8")
    assert src.isascii(), "non-ASCII characters found; write them as escapes"


def test_every_interface_language_has_every_text_and_it_decodes_to_the_right_script():
    import shutil
    import subprocess
    from pathlib import Path
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    src = (Path(__file__).resolve().parent.parent / "static" / "widget.js").read_text(encoding="utf-8")
    block = src[src.index("var I18N = {"):src.index("};", src.index("var I18N = {")) + 2]
    script = block + "; console.log(JSON.stringify(I18N));"
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, encoding="utf-8", check=True)
    table = json.loads(out.stdout)
    from noah.lang import detect_script
    assert set(table) == set(NATIVE)
    english_keys = set(table["en"])
    for code, texts in table.items():
        assert all(isinstance(v, str) and v.strip() for v in texts.values()), code
        if code != "en":
            # every translated screen title is genuinely in that language's script and has no mojibake
            for key in ("placeholder", "send", "tools", "advisor", "callback", "visit", "documents", "careers", "events", "wellness", "student"):
                assert detect_script(texts[key]) == code, (code, key, texts[key])
            assert not any(bad in "".join(texts.values()) for bad in MOJIBAKE), code
            assert english_keys >= set(texts) and set(texts) >= {"placeholder", "send", "tools", "back", "close", "privacy", "welcome"}, code


def test_translation_helper_round_trips_all_scripts(fake):
    # the translator tags its output "[xx]"; non-ASCII input must survive the trip through JSON mode
    out = brain._translate([NATIVE["hi"], NATIVE["ta"]], "kn")
    assert out == ["[xx] " + NATIVE["hi"], "[xx] " + NATIVE["ta"]]
