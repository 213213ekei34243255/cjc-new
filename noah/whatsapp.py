"""Feature 6 - the same brain on WhatsApp (Meta WhatsApp Cloud API).

Setup lives in the README. Safe by default: with no WHATSAPP_* variables the routes answer 503, and a
POST is only processed when its X-Hub-Signature-256 matches WHATSAPP_APP_SECRET. Meta retries a webhook
that does not answer within a few seconds, so we reply 200 at once and work in a background thread,
remembering message ids to ignore the retries.
"""

import hashlib
import hmac
import logging
import re
import threading
import time

import requests
from flask import Blueprint, jsonify, request

from . import brain, config, sessions
from .features import leads
from .limiter import limiter
from .store import StoreError, get_store

log = logging.getLogger("noah.whatsapp")
whatsapp_bp = Blueprint("noah_whatsapp", __name__)

_seen = {}
_seen_lock = threading.Lock()
SITE = "https://christjuniorcollege.in"

_PANEL_HINT = {
    "advisor": "For the Stream Advisor, chat with me on " + SITE,
    "visit": "To book a campus visit, use the chat on " + SITE + " or reply CALL and the office will arrange it.",
    "documents": "Reply DOCS for the document list.",
    "careers": "The Careers explorer is in the chat on " + SITE,
    "events": "Event details are in the chat on " + SITE,
    "compare": "Reply COMPARE for PU vs IBDP.",
    "wellness": "",
    "callback": "Reply CALL and the admissions office will phone you on this number.",
    "student": "", "study": "", "staff": "",
}


def configured():
    return bool(config.WA_VERIFY_TOKEN and config.WA_ACCESS_TOKEN and config.WA_PHONE_NUMBER_ID and config.WA_APP_SECRET)


def verify_signature(raw_body, header):
    if not config.WA_APP_SECRET or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(config.WA_APP_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[7:])


def sender_id(wa_number):
    """Stable pseudonymous session id so raw phone numbers are not written to the chat log."""
    return "wa-" + hashlib.sha256(wa_number.encode()).hexdigest()[:20]


def render(reply):
    """Flatten a Reply into WhatsApp text: answer, key card facts, links, next-step hints."""
    lines = [reply.answer.strip()]
    for card in reply.cards:
        if card["type"] == "fees":
            lines.append("\n".join(f"- {r['code']}: {r['value']}" for r in card["rows"]))
        elif card["type"] == "contact":
            lines.append("\n".join(f"{r['label']}: {r['value']}" for r in card["rows"]))
        elif card["type"] == "helplines":
            lines.append("\n".join(f"{r['name']}: {r['phone']}" for r in card["rows"]))
    if reply.url:
        lines.append(reply.url)
    for link in reply.links:
        lines.append(f"{link['label']}: {link['url']}")
    for action in reply.actions:
        hint = _PANEL_HINT.get(action.get("open"), "")
        if hint:
            lines.append(hint)
    return "\n\n".join(l for l in lines if l)[:4000]


def send_text(to, text):
    if not configured():
        return False
    url = f"{config.WA_GRAPH_BASE}/{config.WA_GRAPH_VERSION}/{config.WA_PHONE_NUMBER_ID}/messages"
    try:
        resp = requests.post(url, headers={"Authorization": f"Bearer {config.WA_ACCESS_TOKEN}"}, timeout=15,
                             json={"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text, "preview_url": True}})
        if not resp.ok:
            log.warning("WhatsApp send failed: %s %s", resp.status_code, resp.text[:200])
        return resp.ok
    except requests.RequestException as exc:
        log.warning("WhatsApp send error: %s", exc)
        return False


def _remember_id(message_id):
    now = time.time()
    with _seen_lock:
        for k in [k for k, t in _seen.items() if now - t > 3600]:
            del _seen[k]
        if message_id in _seen:
            return False
        _seen[message_id] = now
        return True


def handle_text(wa_number, name, text, store=None):
    """Return the text to send back. Separate from HTTP so it can be tested without Meta."""
    store = store or get_store()
    sid = sender_id(wa_number)
    cmd = text.strip().lower()
    pending = sessions.cache_get("wa-pending:" + sid)

    if pending == "callback" and cmd in ("yes", "y", "haan", "ok", "okay"):
        sessions.cache_set("wa-pending:" + sid, None, 1)
        try:
            res = leads.create_callback(store, {"name": name or "WhatsApp visitor", "phone": wa_number, "consent": True,
                                                "note": "Requested on WhatsApp"}, source="whatsapp")
            return f"Done. The admissions office will call you on this number. Your reference is {res['ref']}."
        except (leads.ValidationError, StoreError):
            return "I could not save that request. Please call +91 080 4012 9292 (Mon-Fri 8:30-4:30)."
    if cmd in ("call", "callback", "call me"):
        sessions.cache_set("wa-pending:" + sid, "callback", 600)
        return ("The admissions office can call you back. Reply YES to confirm that we may phone you on this number. "
                "Your number is used only to contact you about admissions.")
    if cmd in ("docs", "documents"):
        text = "what documents are needed for admission"
    if cmd == "compare":
        text = "compare PU and IBDP"

    ctx = brain.Ctx(text=text, sid=sid, lang_pref="en", channel="whatsapp")
    reply = brain.respond(ctx, store)
    return render(reply)


def _process(entry_changes):
    for change in entry_changes:
        value = change.get("value", {})
        names = {c.get("wa_id"): (c.get("profile") or {}).get("name", "") for c in value.get("contacts", [])}
        for msg in value.get("messages", []):
            if msg.get("type") != "text" or not _remember_id(msg.get("id", "")):
                continue
            number = msg.get("from", "")
            if not limiter.allow("wa", number, 10, 60):
                continue
            try:
                text = handle_text(number, names.get(number, ""), msg["text"]["body"])
            except Exception:  # noqa: BLE001 - never let one bad message kill the worker
                log.exception("WhatsApp handling failed")
                text = "Sorry, something went wrong. Please call the college office on +91 080 4012 9292."
            send_text(number, text)


@whatsapp_bp.get("/webhook/whatsapp")
def verify():
    if not configured():
        return "WhatsApp is not configured", 503
    if request.args.get("hub.mode") == "subscribe" and hmac.compare_digest(request.args.get("hub.verify_token", ""), config.WA_VERIFY_TOKEN):
        return request.args.get("hub.challenge", ""), 200
    return "Forbidden", 403


@whatsapp_bp.post("/webhook/whatsapp")
def incoming():
    if not configured():
        return jsonify({"error": "WhatsApp is not configured"}), 503
    raw = request.get_data()
    if not verify_signature(raw, request.headers.get("X-Hub-Signature-256", "")):
        return jsonify({"error": "bad signature"}), 403
    payload = request.get_json(silent=True) or {}
    changes = [c for e in payload.get("entry", []) for c in e.get("changes", [])]
    threading.Thread(target=_process, args=(changes,), daemon=True).start()
    return jsonify({"ok": True}), 200
