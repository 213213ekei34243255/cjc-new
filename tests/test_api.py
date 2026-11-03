import hashlib
import hmac
import json
import re
from datetime import datetime, timedelta

from noah import brain, config, sessions, whatsapp
from noah.features import events as events_feature

ORIGIN = "https://christjuniorcollege.in"
GOOD_LEAD = {"name": "Asha Rao", "phone": "9876543210", "consent": True}


def post(client, path, data=None, headers=None):
    return client.post(path, json=data or {}, headers=headers or {})


# ---- chat endpoints + CORS ------------------------------------------------------------------------------
def test_predict_keeps_the_old_contract_and_adds_new_fields(client, fake):
    r = post(client, "/predict", {"message": "fees for PCMB", "session_id": "sess-api-0001", "url": "https://x/y?z=1"})
    j = r.json
    assert r.status_code == 200 and "80,000" in j["answer"] and j["reply_id"] and j["cards"][0]["type"] == "fees"


def test_predict_validation_and_nav_command(client):
    assert post(client, "/predict", {"message": ""}).status_code == 400
    j = post(client, "/predict", {"message": "open ibdp faqs", "session_id": "sess-api-0002"}).json
    assert j["url"] == "https://christjuniorcollege.in/admission-faqs-ibdp.php"
    j = post(client, "/predict", {"message": "open https://example.org/x", "session_id": "sess-api-0003"}).json
    assert j["url"] == "https://example.org/x"


def test_cors_allows_the_college_origin_only(client):
    ok = client.options("/predict/stream", headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST",
                                                      "Access-Control-Request-Headers": "content-type,x-student-token"})
    assert ok.headers.get("Access-Control-Allow-Origin") == ORIGIN
    assert "x-student-token" in ok.headers.get("Access-Control-Allow-Headers", "").lower()
    bad = client.options("/api/callback", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert "Access-Control-Allow-Origin" not in bad.headers
    api = client.get("/api/health", headers={"Origin": ORIGIN})
    assert api.headers.get("Access-Control-Allow-Origin") == ORIGIN


def test_stream_endpoint_speaks_sse(client, fake):
    r = client.post("/predict/stream", json={"message": "tell me about the library", "session_id": "sess-api-0004"})
    assert r.mimetype == "text/event-stream" and r.headers["X-Accel-Buffering"] == "no"
    events = [json.loads(line[6:]) for line in r.get_data(as_text=True).split("\n\n") if line.startswith("data: ")]
    assert events[-1]["type"] == "final" and any(e["type"] == "delta" for e in events)
    assert events[-1]["reply"]["answer"].startswith("Gemini says")


def test_chat_rate_limit(client, monkeypatch):
    monkeypatch.setattr(config, "RATE_CHAT_PER_MIN_SESSION", 3)
    codes = [post(client, "/predict", {"message": f"fees for PCMB {i}", "session_id": "sess-api-rate"}).status_code for i in range(5)]
    assert codes == [200, 200, 200, 429, 429]


def test_bad_session_ids_are_replaced(client):
    j = post(client, "/predict", {"message": "fees for PCMB", "session_id": "<script>"}).json
    assert j["reply_id"]


# ---- feedback + staff inbox loop --------------------------------------------------------------------------------------
def test_feedback_thumbs_down_lands_in_staff_inbox_and_teaches_noah(client, fake, staff_headers):
    sid = "sess-api-fb01"
    r = post(client, "/predict", {"message": "UNKNOWNQ do you have a swimming pool", "session_id": sid}).json
    assert r["engine"] == "gemini"
    assert post(client, "/api/feedback", {"reply_id": r["reply_id"], "session_id": "someone-else-1", "vote": "down"}).status_code == 404
    assert post(client, "/api/feedback", {"reply_id": r["reply_id"], "session_id": sid, "vote": "down", "comment": "wrong"}).status_code == 200

    inbox = client.get("/api/staff/unanswered", headers=staff_headers).json
    assert inbox["open"][0]["count"] == 2                         # once as unknown, once as thumbs-down
    assert inbox["disliked"][0]["comment"] == "wrong" and "swimming pool" in inbox["disliked"][0]["question"]
    item = inbox["open"][0]
    assert post(client, f"/api/staff/unanswered/{item['id']}/answer", {"answer": "Yes, the college has a swimming pool open to all students."}, staff_headers).status_code == 200

    again = post(client, "/predict", {"message": "UNKNOWNQ do you have a swimming pool", "session_id": "sess-api-fb02"}).json
    assert again["intent"] == "learned" and "swimming pool" in again["answer"]
    assert client.get("/api/staff/unanswered", headers=staff_headers).json["open"] == []


# ---- staff auth ------------------------------------------------------------------------------------------------------------------
def test_staff_routes_need_the_password_and_token(client):
    assert client.get("/api/staff/overview").status_code == 401
    assert post(client, "/api/staff/login", {"password": "nope"}).status_code == 401
    assert client.get("/api/staff/overview", headers={"Authorization": "Bearer forged.token.here"}).status_code == 401


def test_staff_login_is_rate_limited(client):
    codes = [post(client, "/api/staff/login", {"password": "x"}).status_code for _ in range(8)]
    assert 429 in codes


def test_staff_disabled_without_a_password_and_the_message_says_why(client, monkeypatch):
    monkeypatch.setattr(config, "STAFF_PASSWORD", "")
    r = post(client, "/api/staff/login", {"password": "anything"})
    assert r.status_code == 503 and "no STAFF_PASSWORD" in r.json["error"] and "Environment" in r.json["error"]
    assert client.get("/api/staff/overview").json["error"] == r.json["error"]
    assert client.get("/api/health").json["staff"] == "missing"


def test_staff_disabled_with_a_too_short_password(client, monkeypatch):
    monkeypatch.setattr(config, "STAFF_PASSWORD", "short")
    r = post(client, "/api/staff/login", {"password": "short"})
    assert r.status_code == 503 and "shorter than 10" in r.json["error"]
    assert client.get("/api/health").json["staff"] == "too_short"


def test_student_token_cannot_open_staff_routes(client, fresh):
    code = fresh.create_student_code("II PUC")
    token = post(client, "/api/student/login", {"code": code}).json["token"]
    assert client.get("/api/staff/overview", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_staff_overview_and_analytics(client, fake, staff_headers):
    post(client, "/predict", {"message": "fees for PCMB", "session_id": "sess-api-an01", "url": "https://christjuniorcollege.in/faqs-pu.php?x=1"})
    post(client, "/predict", {"message": "I feel very anxious", "session_id": "sess-api-an02"})
    j = client.get("/api/staff/overview", headers=staff_headers).json
    a = j["analytics"]
    assert a["questions"] == 2 and a["private_chats"] == 1 and a["top_pages"][0]["page"] == "https://christjuniorcollege.in/faqs-pu.php"
    assert a["top_questions"][0]["norm"] == "fees for pcmb"
    assert "test-key" not in json.dumps(j) and j["llm"]["primary"]["name"] == "Rexy CogniAI's Foundational Model"


# ---- leads, visits, counselling ------------------------------------------------------------------------------------------------------
def test_callback_visit_and_counselling_flow_into_the_staff_panel(client, staff_headers, monkeypatch):
    sent = []
    monkeypatch.setattr("noah.notify.lead_created", lambda kind, lead: sent.append((kind, lead["id"])))
    assert post(client, "/api/callback", {**GOOD_LEAD, "interest": "ibdp"}).status_code == 200
    bad = post(client, "/api/callback", {**GOOD_LEAD, "phone": "123"})
    assert bad.status_code == 400 and bad.json["field"] == "phone"

    slots = client.get("/api/visit/slots").json
    day = slots["days"][0]
    book = post(client, "/api/visit/book", {**GOOD_LEAD, "date": day["date"], "time": day["slots"][0]["time"]})
    assert book.status_code == 200 and book.json["place"]
    assert post(client, "/api/wellness/counselling", {**GOOD_LEAD, "class_name": "I PUC"}).status_code == 200
    assert [k for k, _ in sent] == ["callback", "visit", "counselling"]

    rows = client.get("/api/staff/leads", headers=staff_headers).json["leads"]
    assert {r["kind"] for r in rows} == {"callback", "visit", "counselling"}
    lead_id = rows[0]["id"]
    assert client.patch(f"/api/staff/leads/{lead_id}", json={"status": "contacted", "staff_note": "called"}, headers=staff_headers).json["ok"]
    csv_text = client.get("/api/staff/leads.csv", headers=staff_headers).get_data(as_text=True)
    assert "Asha Rao" in csv_text and csv_text.startswith("id,ts,kind")


def test_csv_export_neutralises_formula_injection(client, staff_headers):
    post(client, "/api/callback", {"name": "=HYPERLINK(\"http://evil\")", "phone": "9876543210", "consent": True})
    assert "'=HYPERLINK" in client.get("/api/staff/leads.csv", headers=staff_headers).get_data(as_text=True)


def test_honeypot_pretends_success_but_saves_nothing(client, staff_headers):
    assert post(client, "/api/callback", {**GOOD_LEAD, "website": "http://spam"}).json["ok"]
    assert client.get("/api/staff/leads", headers=staff_headers).json["leads"] == []


def test_visit_double_booking_returns_409(client):
    day = client.get("/api/visit/slots").json["days"][0]
    slot = {"date": day["date"], "time": day["slots"][0]["time"]}
    for i in range(3):
        post(client, "/api/visit/book", {**GOOD_LEAD, "name": f"Parent {i}", **slot})
    assert post(client, "/api/visit/book", {**GOOD_LEAD, **slot}).status_code == 409


def test_form_endpoints_share_a_per_ip_hourly_limit(client):
    limit = config.RATE_FORMS_PER_HOUR_IP
    codes = [post(client, "/api/callback", GOOD_LEAD).status_code for _ in range(limit + 2)]
    assert codes == [200] * limit + [429, 429]


# ---- wellness API: nothing is stored ---------------------------------------------------------------------------------------------------
def test_wellness_checkin_endpoint_stores_nothing(client, fresh, fake):
    j = post(client, "/api/wellness/checkin", {"mood": 2, "concerns": ["Feeling alone"], "lang": "kn"}).json
    assert j["show_helplines"] and j["headline"].startswith("[xx]")
    assert fresh._connect().execute("SELECT COUNT(*) n FROM messages").fetchone()["n"] == 0
    assert fresh.list_leads() == []


def test_wellness_can_be_switched_off(client, monkeypatch):
    monkeypatch.setattr(config, "WELLNESS_ENABLED", False)
    assert post(client, "/api/wellness/checkin", {"mood": 3}).status_code == 404
    assert post(client, "/predict", {"message": "I am stressed", "session_id": "sess-api-wl"}).json["intent"] != "tool:wellness"
    assert post(client, "/predict", {"message": "I want to die", "session_id": "sess-api-wl2"}).json["intent"] == "crisis"   # safety net stays on


# ---- student zone ---------------------------------------------------------------------------------------------------------------------------
def test_student_zone_requires_a_valid_unrevoked_code(client, fresh, fake, staff_headers):
    assert client.get("/api/student/exams").status_code == 401
    assert client.post("/api/study/quiz", json={"subject": "Physics", "topic": "light"}).status_code == 401
    created = post(client, "/api/staff/student-codes", {"label": "II PUC PCMB 2026-27", "course": "II PUC", "days": 30}, staff_headers).json
    code = created["code"]
    assert post(client, "/api/student/login", {"code": "CJC-BAD00-CODE0"}).status_code == 401
    login = post(client, "/api/student/login", {"code": code}).json
    h = {"X-Student-Token": login["token"]}
    plan = client.get("/api/student/exams?subjects=Physics,Mathematics", headers=h).json
    assert plan["rows"] and "Physics" in plan["subjects"]
    quiz = post(client, "/api/study/quiz", {"subject": "Physics", "topic": "Newton's laws", "count": 5}, h)
    assert quiz.status_code == 200 and len(quiz.json["questions"]) == 5

    listed = client.get("/api/staff/student-codes", headers=staff_headers).json["codes"]
    assert code not in json.dumps(listed)                                   # only the hint is kept
    client.delete(f"/api/staff/student-codes/{listed[0]['id']}", headers=staff_headers)
    assert client.get("/api/student/exams", headers=h).status_code == 401  # revoked codes cut off live tokens


def test_study_mode_chat_with_token(client, fresh, fake):
    token = post(client, "/api/student/login", {"code": fresh.create_student_code("II PUC")}).json["token"]
    j = post(client, "/predict", {"message": "explain refraction", "session_id": "sess-api-study", "mode": "study"}, {"X-Student-Token": token}).json
    assert j["intent"] == "study" and j["answer"].startswith("Tutor says")
    nope = post(client, "/predict", {"message": "explain refraction", "session_id": "sess-api-study2", "mode": "study"}).json
    assert nope["actions"][0]["open"] == "student"


def test_study_errors_are_friendly(client, fresh, fake):
    token = post(client, "/api/student/login", {"code": fresh.create_student_code("II PUC")}).json["token"]
    h = {"X-Student-Token": token}
    r = post(client, "/api/study/quiz", {"subject": "Physics", "topic": "NOTSTUDY"}, h)
    assert r.status_code == 503 and "school subject" in r.json["error"]


# ---- events + timetable via staff ----------------------------------------------------------------------------------------------------------------
def test_events_api_reports_christmas_and_events_that_are_over(client):
    by_id = {e["id"]: e for e in client.get("/api/events").json["events"]}
    assert by_id["christmas-2026"]["starts"] == "2026-12-05" and by_id["christmas-2026"]["ends"] == "2026-12-31"
    assert by_id["xite"]["status"] == "over" and by_id["magnachrista"]["status"] == "over"
    assert by_id["magnasports"]["status"] == "dates_tba"


def test_staff_can_mark_an_event_over(client, staff_headers):
    saved = post(client, "/api/staff/events", {"id": "magnasports", "title": "Magnasports", "over": True}, staff_headers)
    assert saved.status_code == 200 and saved.json["event"]["over"] is True
    by_id = {e["id"]: e for e in client.get("/api/events").json["events"]}
    assert by_id["magnasports"]["status"] == "over"


def test_staff_can_set_event_dates_and_replace_the_timetable(client, fake, staff_headers):
    start = (datetime.now(events_feature.IST) + timedelta(days=10)).date().isoformat()
    ev = post(client, "/api/staff/events", {"id": "cjc-mun-2026", "title": "CJC MUN 2026", "starts": start, "sort": 1, "link_url": "https://cjcmun.com"}, staff_headers)
    assert ev.status_code == 200
    mun = next(e for e in client.get("/api/events").json["events"] if e["id"] == "cjc-mun-2026")
    assert mun["days_left"] == 10 and mun["status"] == "upcoming"
    assert post(client, "/api/staff/events", {"title": "Bad", "link_url": "javascript:1"}, staff_headers).status_code == 400

    tt = {"title": "Prelims", "schedule": [{"date": "01.03.2027", "day": "Monday", "subjects": [{"name": "Physics", "code": "33"}]}]}
    assert client.put("/api/staff/timetable", json={"timetable": tt}, headers=staff_headers).status_code == 200
    assert client.put("/api/staff/timetable", json={"timetable": {"schedule": []}}, headers=staff_headers).status_code == 400
    assert client.get("/api/staff/timetable", headers=staff_headers).json["timetable"]["title"] == "Prelims"
    client.delete("/api/staff/timetable", headers=staff_headers)
    assert client.get("/api/staff/timetable", headers=staff_headers).json["custom"] is False


# ---- public data endpoints -------------------------------------------------------------------------------------------------------------------------
def test_data_endpoints(client):
    q = client.get("/api/advisor/questions").json
    assert [s["id"] for s in q["questions"]][:2] == ["board", "percent"]
    rec = post(client, "/api/advisor/recommend", {"answers": {"percent": 85, "interests": ["bio"], "goal": "doctor"}}).json
    assert rec["results"][0]["code"] == "PCMB"
    assert post(client, "/api/advisor/recommend", {"answers": {}}).status_code == 400
    assert client.get("/api/compare").json["rows"]
    assert client.get("/api/checklist?program=pu&board=cbse").json["items"][-1]["id"] == "consumer"
    assert client.get("/api/checklist?program=pu&board=zzz").status_code == 400
    assert len(client.get("/api/careers").json["paths"]) == 8
    ctx = client.get("/api/context?url=https://christjuniorcollege.in/about-us-ibdp.php").json
    assert ctx["topic"] == "ibdp" and {l["code"] for l in ctx["languages"]} == {"en", "kn", "hi", "ta", "ml", "te"}
    assert client.get("/api/wellness/info").json["helplines"][0]["phone"] == "14416"


def test_health_reports_primary_model(client):
    j = client.get("/api/health").json
    assert j == {"ok": True, "ai": "gemini", "db": True, "staff": "ok", "email": False, "widget": j["widget"], "storage": j["storage"]}
    assert j["storage"] in ("disk", "folder", "local")                # "disk" = the data survives a restart
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}\.\d+", j["widget"])
    assert "correct-horse" not in str(j)                               # yes/no only, never a value


# ---- WhatsApp ------------------------------------------------------------------------------------------------------------------------------------
def sign(body: bytes, secret="app-secret"):
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_whatsapp_verification_handshake(client):
    ok = client.get("/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=verify-me&hub.challenge=777")
    assert ok.status_code == 200 and ok.get_data(as_text=True) == "777"
    assert client.get("/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=wrong&hub.challenge=1").status_code == 403


def test_whatsapp_rejects_unsigned_and_wrongly_signed_posts(client):
    body = json.dumps({"entry": []}).encode()
    assert client.post("/webhook/whatsapp", data=body, content_type="application/json").status_code == 403
    assert client.post("/webhook/whatsapp", data=body, content_type="application/json", headers={"X-Hub-Signature-256": sign(body, "other")}).status_code == 403
    assert client.post("/webhook/whatsapp", data=body, content_type="application/json", headers={"X-Hub-Signature-256": sign(body)}).status_code == 200


def test_whatsapp_message_gets_a_reply_through_the_graph_api(client, fake, monkeypatch):
    sent = []
    monkeypatch.setattr(whatsapp, "send_text", lambda to, text: sent.append((to, text)) or True)
    payload = {"entry": [{"changes": [{"value": {"contacts": [{"wa_id": "919876543210", "profile": {"name": "Asha"}}],
                                                 "messages": [{"id": "wamid.1", "from": "919876543210", "type": "text", "text": {"body": "fees for PCMB"}}]}}]}]}
    body = json.dumps(payload).encode()
    h = {"X-Hub-Signature-256": sign(body)}
    client.post("/webhook/whatsapp", data=body, content_type="application/json", headers=h)
    client.post("/webhook/whatsapp", data=body, content_type="application/json", headers=h)       # Meta retry
    import time
    for _ in range(50):
        if sent:
            break
        time.sleep(0.05)
    time.sleep(0.2)
    assert len(sent) == 1 and sent[0][0] == "919876543210" and "80,000" in sent[0][1]


def test_whatsapp_callback_needs_explicit_yes(fresh, fake):
    number = "919876543210"
    assert "Reply YES" in whatsapp.handle_text(number, "Asha", "call me")
    assert fresh.list_leads() == []
    out = whatsapp.handle_text(number, "Asha", "yes")
    assert "CJC-C" in out
    lead = fresh.list_leads("callback")[0]
    assert lead["source"] == "whatsapp" and lead["phone"] == "9876543210" and lead["consent"] == 1
    whatsapp.handle_text(number, "Asha", "yes")                            # a second YES is just a chat message
    assert len(fresh.list_leads("callback")) == 1


def test_whatsapp_uses_pseudonymous_session_ids_and_renders_cards(fresh, fake):
    assert whatsapp.sender_id("919876543210").startswith("wa-") and "9876" not in whatsapp.sender_id("919876543210")
    text = whatsapp.handle_text("919000000000", "", "how do I contact the college")
    assert "4012 9292" in text and "office@cjc.christcollege.edu" in text
    row = fresh._connect().execute("SELECT sid FROM messages LIMIT 1").fetchone()
    assert row["sid"].startswith("wa-")


def test_whatsapp_crisis_reply_carries_helplines(fresh, fake):
    assert "14416" in whatsapp.handle_text("919111111111", "", "I want to end my life")


def test_whatsapp_off_without_config(client, monkeypatch):
    monkeypatch.setattr(config, "WA_APP_SECRET", "")
    assert client.get("/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=verify-me&hub.challenge=1").status_code == 503
