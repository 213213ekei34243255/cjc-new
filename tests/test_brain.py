import json

from noah import brain, config, sessions
from noah.features import wellness


def ask(text, sid="sess-0001", **kw):
    return brain.respond(brain.Ctx(text=text, sid=sid, **kw))


def test_fee_answer_is_deterministic_and_never_touches_a_model(fake):
    r = ask("What is the fee for PCMB?")
    assert "80,000" in r.answer and "not monthly" in r.answer
    assert r.engine == "rules" and r.cards[0]["type"] == "fees"
    assert not fake.gemini_calls and not fake.llama_calls


def test_category_fee_lists_every_substream(fake):
    r = ask("commerce fees please")
    assert "CAMS" in r.answer and "CAME" in r.answer and "90,000" in r.answer


def test_monthly_fee_question_is_corrected_not_invented(fake):
    r = ask("what is the monthly fee for class 11")
    assert "not monthly" in r.answer


def test_old_substring_bug_starts_no_longer_returns_arts_fees(fake):
    r = ask("when do the classes starts")
    assert r.intent == "llm" and "HEPP" not in r.answer
    assert fake.gemini_calls                                    # went to the model, not the fee table


def test_off_topic_guard_uses_word_boundaries(fake):
    assert ask("Who is the best actor?").intent == "offtopic"
    r = ask("what is the cutoff factor for PCMB")
    assert r.intent != "offtopic"
    assert ask("is there a filmmaking club").intent != "offtopic"


def test_crisis_beats_everything_and_is_never_logged(fake, fresh):
    r = ask("I want to kill myself", sid="sess-crisis")
    assert r.intent == "crisis" and r.private and r.cards[0]["type"] == "helplines"
    assert "14416" in json.dumps(r.cards) and "112" in json.dumps(r.cards)
    assert not fake.gemini_calls
    rows = fresh._connect().execute("SELECT text, private FROM messages").fetchall()
    assert rows and all(row["private"] == 1 and row["text"] == "" for row in rows)
    assert sessions.load_history("sess-crisis") == []


def test_crisis_in_hindi_and_kannada_script(fake):
    assert ask("मुझे आत्महत्या के विचार आते हैं").intent == "crisis"
    assert ask("ನನಗೆ ಆತ್ಮಹತ್ಯೆ ಯೋಚನೆ ಬರುತ್ತಿದೆ").intent == "crisis"


def test_model_flagged_crisis_in_any_language_swaps_in_helplines(fake):
    r = ask("MODELCRISIS something indirect")
    assert r.intent == "crisis" and r.cards[0]["type"] == "helplines"


def test_tool_intents_open_panels(fake):
    cases = {
        "which stream should I choose?": "advisor",
        "please call me back": "callback",
        "I want to visit the campus": "visit",
        "what documents are needed": "documents",
        "what can I do after PCMB": "careers",
        "any upcoming events": "events",
        "pu vs ibdp which is better": "compare",
        "I'm so stressed about exams": "wellness",
    }
    for text, panel in cases.items():
        r = ask(text, sid="sess-" + panel)
        assert r.actions and r.actions[0]["open"] == panel, text
    assert not fake.gemini_calls


def test_careers_intent_preselects_the_stream(fake):
    r = ask("career after PCMC")
    assert r.actions[0] == {"open": "careers", "args": {"path": "PCMC"}}


def test_wellness_intent_is_private(fake, fresh):
    ask("I feel very anxious", sid="sess-w")
    rows = fresh._connect().execute("SELECT text, private FROM messages").fetchall()
    assert all(r["private"] == 1 for r in rows)


def test_student_tools_need_a_student(fake):
    assert ask("quiz me", sid="sess-a").actions[0]["open"] == "student"
    assert ask("quiz me", sid="sess-b", student={"cid": 1}).actions[0]["open"] == "study"


def test_llm_answer_gets_chips_links_and_is_logged(fake, fresh):
    r = ask("How do I apply for IBDP admission process?")
    assert r.engine == "gemini" and r.answer.startswith("Gemini says")
    assert r.chips and r.links
    assert fresh._connect().execute("SELECT COUNT(*) n FROM messages").fetchone()["n"] == 2


def test_gemini_prompt_contains_the_whole_fact_sheet_and_identity(fake):
    ask("tell me something about the campus library")
    system = fake.gemini_calls[0]["body"]["systemInstruction"]["parts"][0]["text"]
    for needle in ("Noah", "CogniAI Studios", "PCMB", "Dharmaram", "5L", "PRIVACY", "EXAM TIMETABLE", "EVENTS AND CAMPAIGNS", "cjcmun.com"):
        assert needle in system
    assert "Today is" in system


def test_model_down_everywhere_gives_office_fallback_and_logs_it(fake, fresh):
    fake.gemini_mode, fake.llama_mode = "500", "500"
    r = ask("tell me about lab facilities")
    assert r.engine == "none" and "4012 9292" in r.answer
    assert fresh.list_unanswered()[0]["reason"] == "model_unavailable"


def test_qwen_backup_answers_with_short_prompt_and_length_limit(fake):
    fake.gemini_mode = "500"
    r = ask("what about the library timings")
    assert r.engine == "qwen" and r.answer.startswith("Qwen says")
    system = fake.llama_calls[0]["messages"][0]["content"]
    assert len(system) < 6000 and "FACTS:" in system             # small context, not the whole sheet


def test_unknown_marker_records_unanswered_and_hides_marker(fake, fresh):
    r = ask("UNKNOWNQ what is the canteen menu")
    assert r.unknown and "[[" not in r.answer
    assert r.cards[0]["type"] == "contact"
    items = fresh.list_unanswered()
    assert items and "canteen menu" in items[0]["question"]


def test_open_marker_becomes_an_action_and_is_stripped(fake):
    r = ask("OPENADVISOR help")
    assert r.actions == [{"open": "advisor"}] and "[[" not in r.answer


def test_wrong_fee_from_model_is_replaced(fake):
    r = ask("WRONGFEE tell me the PCMB charge")
    assert "12,345" not in r.answer


def test_first_turn_answers_are_cached(fake):
    ask("tell me about the campus facilities", sid="sess-c1")
    n = len(fake.gemini_calls)
    r = ask("Tell me about the campus facilities!", sid="sess-c2")
    assert r.engine == "cache" and len(fake.gemini_calls) == n


def test_follow_ups_are_not_cached_and_use_history(fake):
    ask("tell me about the library", sid="sess-h")
    ask("and the timings?", sid="sess-h")
    contents = fake.gemini_calls[-1]["body"]["contents"]
    assert len(contents) >= 3 and contents[-1]["parts"][0]["text"] == "and the timings?"


def test_staff_taught_answer_is_used_and_clears_cache(fake, fresh):
    ask("what is the canteen menu today", sid="sess-l1")
    fresh.add_learned("What is the canteen menu today?", "The canteen serves a fixed vegetarian menu.")
    r = ask("what is the canteen menu today", sid="sess-l2")
    assert r.intent == "learned" and "vegetarian" in r.answer


def test_non_english_gets_language_rule_and_translated_canned_text(fake):
    r = ask("ಶುಲ್ಕ ಎಷ್ಟು fees", sid="sess-kn")
    assert r.lang == "kn"
    r2 = ask("what are the fees for HESP", sid="sess-kn2", lang_pref="hi")
    assert r2.lang == "hi" and r2.answer.startswith("[xx]")    # fake translator tags translated text
    r3 = ask("tell me about the library hours", sid="sess-kn3", lang_pref="ta")
    system = fake.gemini_calls[-1]["body"]["systemInstruction"]["parts"][0]["text"]
    assert "Reply in Tamil" in system


def test_translation_failure_falls_back_to_english_silently(fake):
    fake.gemini_mode = "500"
    r = ask("what are the fees for HESP", sid="sess-tr", lang_pref="hi")
    assert "55,000" in r.answer and not r.answer.startswith("[xx]")


def test_study_mode_is_gated_and_skips_college_guard(fake):
    assert ask("explain DNA", sid="sess-s1", mode="study").actions[0]["open"] == "student"
    r = ask("explain DNA replication", sid="sess-s1", mode="study", student={"cid": 1})
    assert r.intent == "study" and r.answer.startswith("Tutor says")
    system = fake.gemini_calls[-1]["body"]["systemInstruction"]["parts"][0]["text"]
    assert "study helper" in system and "FACTS ABOUT THE COLLEGE" not in system


def test_stream_emits_deltas_then_final_without_markers(fake):
    events = list(brain.respond_stream(brain.Ctx(text="UNKNOWNQ spell out the canteen rules", sid="sess-st")))
    assert events[-1]["type"] == "final"
    streamed = "".join(e["text"] for e in events if e["type"] == "delta")
    assert "[[" not in streamed and "UNKNOWN" not in streamed
    assert events[-1]["reply"]["answer"].startswith("I do not have that detail")
    assert sum(e["type"] == "delta" for e in events) > 2


def test_stream_for_rule_answers_is_a_single_final(fake):
    events = list(brain.respond_stream(brain.Ctx(text="fees for PCMC", sid="sess-st2")))
    assert [e["type"] for e in events] == ["final"]


def test_stream_falls_back_to_qwen_and_still_finishes(fake):
    fake.gemini_mode = "500"
    events = list(brain.respond_stream(brain.Ctx(text="describe the library", sid="sess-st3")))
    assert events[-1]["reply"]["engine"] == "qwen" and events[-1]["reply"]["answer"].startswith("Qwen says")


def test_page_context_changes_with_the_page():
    assert brain.page_context("https://christjuniorcollege.in/about-us-ibdp.php")["topic"] == "ibdp"
    assert brain.page_context("https://christjuniorcollege.in/contact-us-pu.php")["topic"] == "visit"
    assert brain.page_context("https://christjuniorcollege.in/faqs-pu.php")["topic"] == "pu"
    assert brain.page_context("https://christjuniorcollege.in/")["topic"] == "home"


def test_input_is_clamped(fake):
    r = ask("hello " * 2000)
    assert r.answer
    assert len(fake.gemini_calls[0]["body"]["contents"][-1]["parts"][0]["text"]) <= config.MAX_MESSAGE_CHARS


def test_crisis_regex_has_no_obvious_false_positives():
    for text in ("how do I apply", "I will kill the exam", "fees for commerce", "the library is a quiet place"):
        assert not wellness.is_crisis(text)
