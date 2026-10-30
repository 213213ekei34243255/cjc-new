"""Public JSON API used by widget.js. Everything the college site shows lives inside the widget, so
there are no HTML pages here - only endpoints."""

import logging
from functools import wraps

from flask import Blueprint, jsonify, request

from . import auth, brain, config, knowledge, llm
from .features import advisor, careers, documents, events as events_feature, leads, student, study, wellness
from .lang import LANGS
from .limiter import limiter
from .store import StoreError, get_store

log = logging.getLogger("noah.api")
api_bp = Blueprint("noah_api", __name__, url_prefix="/api")


# ---------------------------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------------------------
def err(message, status=400, **extra):
    return jsonify({"error": message, **extra}), status


def body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def client_ip():
    return request.remote_addr or "unknown"


def limited(bucket, per, window):
    """Per-IP rate limit decorator."""
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if not limiter.allow(bucket, client_ip(), per, window):
                return err("Too many requests. Please wait a moment and try again.", 429)
            return fn(*a, **kw)
        return wrapper
    return deco


def store_guard(fn):
    """The database is a helper, not a dependency of answering questions: report it, never crash."""
    @wraps(fn)
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except StoreError:
            log.exception("store error in %s", fn.__name__)
            return err("This feature is temporarily unavailable. Please call the office on +91 080 4012 9292.", 503)
    return wrapper


def student_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not config.STUDENT_ZONE_ENABLED:
            return err("The Student Zone is switched off.", 404)
        claims = auth.student_from(request, get_store())
        if not claims:
            return err("Please sign in to the Student Zone with your access code.", 401, code="student_auth")
        request.student = claims
        return fn(*a, **kw)
    return wrapper


# ---------------------------------------------------------------------------------------------
# basics
# ---------------------------------------------------------------------------------------------
@api_bp.get("/health")
def health():
    return jsonify({
        "ok": True,
        "ai": "gemini" if llm.gemini_configured() else ("qwen-only" if config.QWEN_ENABLED else "rules-only"),
        "db": get_store().healthy,
    })


@api_bp.get("/context")
def context():
    ctx = brain.page_context(request.args.get("url", ""))
    ctx["languages"] = [{"code": c, "name": v["name"], "native": v["native"], "speech": v["speech"]} for c, v in LANGS.items()]
    ctx["features"] = {"wellness": config.WELLNESS_ENABLED, "student": config.STUDENT_ZONE_ENABLED}
    return jsonify(ctx)


@api_bp.post("/feedback")
@limited("feedback", 60, 60)
@store_guard
def feedback():
    data = body()
    reply_id = str(data.get("reply_id", ""))[:20]
    sid = str(data.get("session_id", ""))[:64]
    vote = 1 if data.get("vote") in (1, "up", True) else -1 if data.get("vote") in (-1, "down") else 0
    if not reply_id or not sid or not vote:
        return err("reply_id, session_id and vote are required")
    store = get_store()
    msg = store.message_for_reply(reply_id)
    if not msg or msg["sid"] != sid:
        return err("Unknown reply", 404)
    store.add_feedback(reply_id, sid, vote, str(data.get("comment", ""))[:500])
    if vote < 0 and msg.get("question") and not msg.get("private"):
        store.record_unanswered(msg["question"], reason="thumbs_down")
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------------------------
# 1. Stream advisor and comparison
# ---------------------------------------------------------------------------------------------
@api_bp.get("/advisor/questions")
def advisor_questions():
    return jsonify({"questions": advisor.QUESTIONS, "admission_status": knowledge.DATA.get("faq", {}).get("admission_status", "")})


@api_bp.post("/advisor/recommend")
@limited("advisor", 40, 60)
def advisor_recommend():
    try:
        return jsonify(advisor.recommend(body().get("answers") or {}))
    except ValueError as exc:
        return err(str(exc))


@api_bp.get("/compare")
def compare():
    return jsonify(advisor.compare())


# ---------------------------------------------------------------------------------------------
# 2. Callback + campus visit
# ---------------------------------------------------------------------------------------------
@api_bp.post("/callback")
@limited("forms", config.RATE_FORMS_PER_HOUR_IP, 3600)
@store_guard
def callback():
    data = body()
    if leads.is_bot(data):
        return jsonify({"ok": True, "ref": "CJC-C00000"})
    try:
        res = leads.create_callback(get_store(), data)
    except leads.ValidationError as exc:
        return err(exc.message, 400, field=exc.field)
    return jsonify({"ok": True, **res})


@api_bp.get("/visit/slots")
@store_guard
def visit_slots():
    return jsonify(leads.available_slots(get_store()))


@api_bp.post("/visit/book")
@limited("forms", config.RATE_FORMS_PER_HOUR_IP, 3600)
@store_guard
def visit_book():
    data = body()
    if leads.is_bot(data):
        return jsonify({"ok": True, "ref": "CJC-V00000"})
    try:
        res = leads.book_visit(get_store(), data)
    except leads.ValidationError as exc:
        return err(exc.message, 409 if exc.field == "slot" else 400, field=exc.field)
    return jsonify({"ok": True, **res})


# ---------------------------------------------------------------------------------------------
# 8, 9, 10. Documents, careers, events
# ---------------------------------------------------------------------------------------------
@api_bp.get("/checklist/options")
def checklist_options():
    return jsonify(documents.options())


@api_bp.get("/checklist")
def checklist():
    try:
        return jsonify(documents.checklist(request.args.get("program", "pu"), request.args.get("board", "state")))
    except ValueError as exc:
        return err(str(exc))


@api_bp.get("/careers")
def careers_all():
    return jsonify(careers.all_paths())


@api_bp.get("/events")
@store_guard
def events_list():
    return jsonify({"events": events_feature.list_events(get_store())})


# ---------------------------------------------------------------------------------------------
# 13. Wellness (nothing here is written to the chat log)
# ---------------------------------------------------------------------------------------------
@api_bp.get("/wellness/info")
def wellness_info():
    d = wellness.data()
    return jsonify({"enabled": config.WELLNESS_ENABLED, "helplines": d["helplines"], "college_line": d["college_line"],
                    "moods": d["moods"], "concerns": d["concerns"], "grounding": d["grounding"]})


@api_bp.post("/wellness/checkin")
@limited("checkin", 60, 60)
def wellness_checkin():
    if not config.WELLNESS_ENABLED:
        return err("The check-in is switched off.", 404)
    data = body()
    result = wellness.checkin(data.get("mood"), data.get("concerns"))
    lang = data.get("lang", "en")
    if lang != "en" and lang in LANGS:
        strings = [result["headline"], result["message"], *result["tips"]]
        out = brain._translate(strings, lang)
        if out:
            result["headline"], result["message"], result["tips"] = out[0], out[1], out[2:]
    return jsonify(result)


@api_bp.post("/wellness/counselling")
@limited("forms", config.RATE_FORMS_PER_HOUR_IP, 3600)
@store_guard
def counselling():
    if not config.WELLNESS_ENABLED:
        return err("Counselling requests are switched off.", 404)
    data = body()
    if leads.is_bot(data):
        return jsonify({"ok": True, "ref": "CJC-N00000"})
    try:
        res = leads.create_counselling(get_store(), data)
    except leads.ValidationError as exc:
        return err(exc.message, 400, field=exc.field)
    return jsonify({"ok": True, **res})


# ---------------------------------------------------------------------------------------------
# 11 + 12. Student Zone and study companion
# ---------------------------------------------------------------------------------------------
@api_bp.post("/student/login")
@limited("student-login", 8, 600)
@store_guard
def student_login():
    if not config.STUDENT_ZONE_ENABLED:
        return err("The Student Zone is switched off.", 404)
    res = student.login(get_store(), str(body().get("code", "")))
    if not res:
        return err("That access code is not valid. Check it with your class teacher.", 401)
    return jsonify(res)


@api_bp.get("/student/exams")
@student_required
@store_guard
def student_exams():
    subjects = [s for s in request.args.get("subjects", "").split(",") if s][:12]
    return jsonify(student.exam_plan(student.timetable_for(get_store()), subjects))


@api_bp.get("/study/subjects")
@student_required
@store_guard
def study_subjects():
    base = ["Physics", "Chemistry", "Mathematics", "Biology", "Computer Science", "Accountancy", "Business Studies",
            "Economics", "Statistics", "History", "Political Science", "Sociology", "Psychology", "English", "Kannada", "Hindi"]
    return jsonify({"subjects": base})


def _study_call(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not limiter.allow("study", getattr(request, "student", {}).get("cid", client_ip()), config.RATE_STUDY_PER_MIN, 60):
            return err("Slow down a little - try again in a minute.", 429)
        try:
            return fn(*a, **kw)
        except study.StudyUnavailable as exc:
            return err(str(exc), 503)
    return wrapper


@api_bp.post("/study/quiz")
@student_required
@_study_call
def study_quiz():
    d = body()
    lang = d.get("lang", "en")
    return jsonify(study.make_quiz(d.get("subject", ""), d.get("topic", ""), d.get("difficulty", "medium"),
                                   d.get("count", 5), LANGS.get(lang, LANGS["en"])["name"]))


@api_bp.post("/study/flashcards")
@student_required
@_study_call
def study_flashcards():
    d = body()
    lang = d.get("lang", "en")
    return jsonify(study.make_flashcards(d.get("subject", ""), d.get("topic", ""), d.get("count", 8),
                                         LANGS.get(lang, LANGS["en"])["name"]))
