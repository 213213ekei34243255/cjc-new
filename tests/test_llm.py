import pytest

from noah import config, llm


def msgs(text="hello"):
    return [{"role": "user", "content": text}]


def test_gemini_is_primary_and_uses_flash_lite_with_key_header(fake):
    res = llm.generate("sys", msgs("hi there"))
    assert res.engine == "gemini" and res.model == "gemini-3.5-flash-lite"
    assert res.text.startswith("Gemini says")
    call = fake.gemini_calls[0]
    assert call["key"] == "test-key"
    assert call["body"]["systemInstruction"]["parts"][0]["text"] == "sys"
    assert not fake.llama_calls                       # Qwen untouched while Gemini works


def test_roles_are_mapped_and_merged_for_gemini(fake):
    llm.generate("s", [{"role": "assistant", "content": "stale"}, {"role": "user", "content": "a"},
                       {"role": "user", "content": "b"}, {"role": "assistant", "content": "c"}, {"role": "user", "content": "d"}])
    contents = fake.gemini_calls[0]["body"]["contents"]
    assert [c["role"] for c in contents] == ["user", "model", "user"]
    assert contents[0]["parts"][0]["text"] == "a\nb"


def test_unknown_model_id_walks_down_the_fallback_chain(fake):
    fake.gemini_mode = "404-first"
    res = llm.generate("s", msgs())
    assert res.engine == "gemini" and res.model == "gemini-3.1-flash-lite"
    assert [c["model"] for c in fake.gemini_calls] == ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
    llm.generate("s", msgs())                         # remembers the working model
    assert fake.gemini_calls[-1]["model"] == "gemini-3.1-flash-lite"


def test_gemini_server_error_falls_back_to_qwen(fake):
    fake.gemini_mode = "500"
    res = llm.generate("s", msgs("question"))
    assert res.engine == "qwen" and res.text.startswith("Qwen says")


def test_empty_gemini_reply_falls_back_to_qwen(fake):
    fake.gemini_mode = "empty"
    assert llm.generate("s", msgs()).engine == "qwen"


def test_circuit_breaker_stops_hammering_a_dead_gemini(fake):
    fake.gemini_mode = "500"
    for _ in range(3):
        llm.generate("s", msgs())
    n = len(fake.gemini_calls)
    assert llm.generate("s", msgs()).engine == "qwen"
    assert len(fake.gemini_calls) == n               # breaker open: Gemini not even called


def test_rejected_key_opens_breaker_immediately(fake):
    fake.gemini_mode = "400"
    assert llm.generate("s", msgs()).engine == "qwen"
    n = len(fake.gemini_calls)
    llm.generate("s", msgs())
    assert len(fake.gemini_calls) == n


def test_no_key_goes_straight_to_qwen(fake, monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    assert llm.generate("s", msgs()).engine == "qwen"
    assert not fake.gemini_calls


def test_both_down_raises(fake):
    fake.gemini_mode, fake.llama_mode = "500", "500"
    with pytest.raises(llm.LLMError):
        llm.generate("s", msgs())


def test_qwen_can_be_disabled(fake, monkeypatch):
    fake.gemini_mode = "500"
    monkeypatch.setattr(config, "QWEN_ENABLED", False)
    with pytest.raises(llm.LLMError):
        llm.generate("s", msgs())


def test_streaming_yields_pieces_then_done(fake):
    events = list(llm.generate_stream("s", msgs("stream me please")))
    deltas = [p for k, p in events if k == "delta"]
    assert len(deltas) > 2
    assert "".join(deltas).startswith("Gemini says: stream me")
    assert events[-1] == ("done", {"engine": "gemini", "model": "gemini-3.5-flash-lite"})
    assert "streamGenerateContent?alt=sse" in fake.gemini_calls[0]["path"]


def test_streaming_falls_back_to_qwen_with_its_own_prompt(fake):
    fake.gemini_mode = "500"
    events = list(llm.generate_stream("HUGE", msgs("hi"), qwen_system="SMALL", qwen_messages=msgs("short")))
    assert "".join(p for k, p in events if k == "delta").startswith("Qwen says: short")
    assert events[-1][1]["engine"] == "qwen"
    assert fake.llama_calls[0]["messages"][0]["content"] == "SMALL"


def test_json_mode_sets_mime_type_and_parse_is_tolerant(fake):
    llm.generate("s", msgs("x"), json_mode=True)
    assert fake.gemini_calls[0]["body"]["generationConfig"]["responseMimeType"] == "application/json"
    assert llm.parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert llm.parse_json('Sure! {"a": [1, 2]} hope that helps') == {"a": [1, 2]}
    with pytest.raises(ValueError):
        llm.parse_json("no json here")


def test_status_never_leaks_the_key():
    assert "test-key" not in str(llm.status())
