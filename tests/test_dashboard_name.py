"""The staff dashboard names the main model "Rexy CogniAI's Foundational Model" and never shows the service behind it."""

import json
import re

from noah import config, llm

NAME = "Rexy CogniAI's Foundational Model"


def post(client, path, data=None, headers=None):
    return client.post(path, json=data or {}, headers=headers or {})


def overview(client, headers):
    r = client.get("/api/staff/overview", headers=headers)
    assert r.status_code == 200
    return r.json


def test_dashboard_shows_the_rexy_name_for_the_main_model(client, staff_headers):
    j = overview(client, staff_headers)
    assert j["llm"]["primary"]["name"] == NAME and j["llm"]["primary"]["configured"] is True


def test_the_display_name_is_a_setting(client, staff_headers, monkeypatch):
    monkeypatch.setattr(config, "MODEL_DISPLAY_NAME", "Rexy 2")
    assert overview(client, staff_headers)["llm"]["primary"]["name"] == "Rexy 2"


def test_no_service_or_model_id_anywhere_in_the_staff_overview(client, fake, staff_headers):
    post(client, "/predict", {"message": "tell me about the library", "session_id": "sess-dash-0001"})      # answered by the main model
    text = json.dumps(overview(client, staff_headers)).lower()
    assert "gemini" not in text and "googleapis" not in text and "flash-lite" not in text


def test_errors_shown_on_the_dashboard_are_scrubbed(client, fake, staff_headers):
    fake.gemini_mode = "500"
    post(client, "/predict", {"message": "tell me about the lab timings", "session_id": "sess-dash-0002"})   # makes the main model fail
    j = overview(client, staff_headers)
    err = j["llm"]["primary"]["breaker"]["last_error"]
    assert err and "gemini" not in err.lower() and "Rexy" in err
    assert "gemini" not in json.dumps(j).lower()


def test_rejected_key_errors_are_scrubbed_too(client, fake, staff_headers):
    fake.gemini_mode = "400"
    post(client, "/predict", {"message": "tell me about the campus", "session_id": "sess-dash-0003"})
    assert "gemini" not in json.dumps(overview(client, staff_headers)).lower()


def test_answered_by_split_calls_the_main_model_rexy(client, fake, staff_headers):
    post(client, "/predict", {"message": "tell me about the library", "session_id": "sess-dash-0004"})
    engines = {e["engine"]: e["n"] for e in overview(client, staff_headers)["analytics"]["engines"]}
    assert engines.get("Rexy") == 1 and "gemini" not in engines


def test_inbox_rows_use_the_display_name_for_the_engine(client, fake, staff_headers):
    sid = "sess-dash-0005"
    reply = post(client, "/predict", {"message": "UNKNOWNQ is there a rooftop garden", "session_id": sid}).json
    post(client, "/api/feedback", {"reply_id": reply["reply_id"], "session_id": sid, "vote": "down"})
    inbox = client.get("/api/staff/unanswered", headers=staff_headers).json
    assert inbox["disliked"][0]["engine"] == "Rexy"
    assert "gemini" not in json.dumps(inbox).lower()


def test_backup_model_line_is_unchanged(client, staff_headers):
    q = overview(client, staff_headers)["llm"]["qwen"]
    assert q["enabled"] is True and "breaker" in q


def test_the_real_service_still_does_the_work(client, fake):
    r = post(client, "/predict", {"message": "tell me about the library", "session_id": "sess-dash-0006"}).json
    assert r["engine"] == "gemini" and fake.gemini_calls                     # only the dashboard label changed


def test_scrub_helper():
    assert llm.scrub("gemini-3.5-flash-lite: HTTP 404") == "Rexy: HTTP 404"
    assert llm.scrub("POST https://generativelanguage.googleapis.com/v1beta failed") == "POST https://Rexy/v1beta failed"
    assert llm.scrub(None) == ""


def test_widget_staff_panel_never_prints_the_service_name():
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent / "static" / "widget.js").read_text(encoding="utf-8")
    assert "gemini" not in src.lower()
    assert "Last Rexy error" in src and "l.primary.name" in src
    assert re.search(r"pal = \{ Rexy:", src)
