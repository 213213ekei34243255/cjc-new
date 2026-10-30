"""Staff tools, delivered as JSON for the staff panel that lives inside widget.js.

Authentication is a bearer token from /api/staff/login (password in the STAFF_PASSWORD environment
variable). Without that variable every staff route answers 503, so a fresh deployment exposes nothing.
"""

import csv
import io
import logging
from functools import wraps

from flask import Blueprint, Response, jsonify, request

from . import auth, config, llm
from .features import events as events_feature, student
from .limiter import limiter
from .store import StoreError, get_store

log = logging.getLogger("noah.staff")
staff_bp = Blueprint("noah_staff", __name__, url_prefix="/api/staff")


def _err(message, status=400):
    return jsonify({"error": message}), status


def staff_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not auth.staff_configured():
            return _err("Staff tools are not configured (set STAFF_PASSWORD, at least 10 characters).", 503)
        if not auth.staff_from(request):
            return _err("Please sign in as staff.", 401)
        try:
            return fn(*a, **kw)
        except StoreError:
            log.exception("store error in %s", fn.__name__)
            return _err("Database error", 503)
    return wrapper


@staff_bp.post("/login")
def login():
    if not auth.staff_configured():
        return _err("Staff tools are not configured.", 503)
    if not limiter.allow("staff-login", request.remote_addr or "?", 6, 300):
        return _err("Too many attempts. Wait five minutes.", 429)
    data = request.get_json(silent=True) or {}
    if not auth.password_matches(str(data.get("password", ""))):
        return _err("Wrong password.", 401)
    return jsonify({"token": auth.staff_token(), "hours": config.STAFF_TOKEN_HOURS})


@staff_bp.get("/overview")
@staff_required
def overview():
    days = max(1, min(180, int(request.args.get("days", 30) or 30)))
    store = get_store()
    return jsonify({"analytics": store.analytics(days), "llm": llm.status(),
                    "retention_days": config.CHAT_RETENTION_DAYS,
                    "notifications": {"email": bool(config.SMTP_HOST and config.ADMISSIONS_EMAIL), "webhook": bool(config.NOTIFY_WEBHOOK_URL),
                                      "whatsapp": bool(config.WA_ACCESS_TOKEN and config.WA_PHONE_NUMBER_ID)}})


# ---- unanswered questions + staff-taught answers --------------------------------------------------
@staff_bp.get("/unanswered")
@staff_required
def unanswered():
    store = get_store()
    return jsonify({"open": store.list_unanswered("open"), "disliked": store.list_disliked(), "learned": store.list_learned()})


@staff_bp.post("/unanswered/<int:item_id>/answer")
@staff_required
def answer_unanswered(item_id):
    text = str((request.get_json(silent=True) or {}).get("answer", "")).strip()
    if len(text) < 5:
        return _err("Write the answer Noah should give (at least a sentence).")
    if not get_store().answer_unanswered(item_id, text[:1200]):
        return _err("Not found", 404)
    return jsonify({"ok": True})


@staff_bp.post("/unanswered/<int:item_id>/dismiss")
@staff_required
def dismiss_unanswered(item_id):
    return jsonify({"ok": get_store().dismiss_unanswered(item_id)})


@staff_bp.post("/learned")
@staff_required
def add_learned():
    d = request.get_json(silent=True) or {}
    q, a = str(d.get("question", "")).strip(), str(d.get("answer", "")).strip()
    if len(q) < 3 or len(a) < 5:
        return _err("A question and an answer are required.")
    return jsonify({"ok": True, "id": get_store().add_learned(q, a[:1200])})


@staff_bp.delete("/learned/<int:learned_id>")
@staff_required
def delete_learned(learned_id):
    return jsonify({"ok": get_store().delete_learned(learned_id)})


# ---- leads, visits, counselling -----------------------------------------------------------------------
@staff_bp.get("/leads")
@staff_required
def leads():
    return jsonify({"leads": get_store().list_leads(request.args.get("kind") or None, request.args.get("status") or None)})


@staff_bp.patch("/leads/<int:lead_id>")
@staff_required
def update_lead(lead_id):
    d = request.get_json(silent=True) or {}
    status = d.get("status")
    if status and status not in ("new", "contacted", "done", "cancelled"):
        return _err("Bad status")
    return jsonify({"ok": get_store().update_lead(lead_id, status, d.get("staff_note"))})


@staff_bp.get("/leads.csv")
@staff_required
def leads_csv():
    rows = get_store().list_leads(limit=5000)
    out = io.StringIO()
    cols = ["id", "ts", "kind", "status", "name", "phone", "email", "role", "board", "interest", "slot_date", "slot_time", "pref_time", "note", "staff_note"]
    writer = csv.writer(out)
    writer.writerow(cols)
    for r in rows:
        # prefix a quote so spreadsheet apps never run a visitor-typed value as a formula
        writer.writerow([("'" + str(r[c]) if str(r[c]).startswith(("=", "+", "-", "@")) else r[c]) for c in cols])
    return Response(out.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=noah-leads.csv"})


# ---- student codes -------------------------------------------------------------------------------------------
@staff_bp.get("/student-codes")
@staff_required
def student_codes():
    return jsonify({"codes": get_store().list_student_codes()})


@staff_bp.post("/student-codes")
@staff_required
def create_student_code():
    d = request.get_json(silent=True) or {}
    label = str(d.get("label", "")).strip()
    if len(label) < 2:
        return _err("Give the code a label, for example 'II PUC PCMB 2026-27'.")
    days = max(1, min(730, int(d.get("days", 365) or 365)))
    code = get_store().create_student_code(label, str(d.get("course", "")), days)
    return jsonify({"code": code, "note": "Copy this now - it cannot be shown again."})


@staff_bp.delete("/student-codes/<int:code_id>")
@staff_required
def revoke_student_code(code_id):
    return jsonify({"ok": get_store().revoke_student_code(code_id)})


# ---- events ------------------------------------------------------------------------------------------------------
@staff_bp.get("/events")
@staff_required
def events():
    store = get_store()
    events_feature.seed(store)
    return jsonify({"events": [events_feature.decorate(e) for e in store.list_events(active_only=False)]})


@staff_bp.post("/events")
@staff_required
def save_event():
    try:
        event = events_feature.validate_event(request.get_json(silent=True) or {})
    except ValueError as exc:
        return _err(str(exc))
    get_store().upsert_event(event)
    return jsonify({"ok": True, "event": event})


@staff_bp.delete("/events/<event_id>")
@staff_required
def delete_event(event_id):
    return jsonify({"ok": get_store().delete_event(event_id)})


# ---- exam timetable --------------------------------------------------------------------------------------------------
@staff_bp.get("/timetable")
@staff_required
def get_timetable():
    store = get_store()
    return jsonify({"timetable": student.timetable_for(store), "custom": bool(store.kv_get("timetable"))})


@staff_bp.put("/timetable")
@staff_required
def put_timetable():
    try:
        tt = student.validate_timetable((request.get_json(silent=True) or {}).get("timetable"))
    except ValueError as exc:
        return _err(str(exc))
    store = get_store()
    store.kv_set("timetable", tt)
    store.bump_version()
    return jsonify({"ok": True})


@staff_bp.delete("/timetable")
@staff_required
def reset_timetable():
    store = get_store()
    store.kv_set("timetable", None)
    store.bump_version()
    return jsonify({"ok": True})


@staff_bp.post("/purge")
@staff_required
def purge():
    return jsonify({"ok": True, "removed": get_store().purge_old()})
