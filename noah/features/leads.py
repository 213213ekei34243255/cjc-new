"""Feature 2 - callback requests, campus-visit bookings; also stores counselling requests (feature 13).

Validation lives here so the HTTP layer and the WhatsApp channel apply the same rules. A request is
saved first and the office is notified afterwards; a failing mail server never loses an enquiry.
"""

import re
from datetime import datetime, timedelta

from .. import notify
from ..store import StoreError
from . import events

_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,200}\.[^@\s]{2,24}$")
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

INTERESTS = {"pu_science", "pu_commerce", "pu_arts", "ibdp", "not_sure"}
BOARDS = {"state", "cbse", "icse", "other", ""}
ROLES = {"parent", "student"}
PREF_TIMES = {"morning", "afternoon", "any"}


class ValidationError(ValueError):
    def __init__(self, field, message):
        super().__init__(message)
        self.field = field
        self.message = message


def clean_text(value, limit):
    return _CTRL.sub("", str(value or "")).strip()[:limit]


def clean_phone(raw):
    digits = re.sub(r"\D", "", str(raw or ""))
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits if re.fullmatch(r"[6-9]\d{9}", digits) else None


def _common(data, need_email=False):
    name = clean_text(data.get("name"), 80)
    if len(name) < 2:
        raise ValidationError("name", "Please enter your name")
    phone = clean_phone(data.get("phone"))
    if not phone:
        raise ValidationError("phone", "Enter a valid 10 digit mobile number")
    email = clean_text(data.get("email"), 120).lower()
    if email and not _EMAIL.match(email):
        raise ValidationError("email", "That email address does not look right")
    if need_email and not email:
        raise ValidationError("email", "Email is required")
    if data.get("consent") is not True:
        raise ValidationError("consent", "Please tick the consent box so the college can contact you")
    return {"name": name, "phone": phone, "email": email, "consent": True}


def _ref(kind, lead_id):
    return f"CJC-{kind[0].upper()}{lead_id:05d}"


def _finish(store, kind, lead_id, fields):
    notify.lead_created(kind, {"id": _ref(kind, lead_id), **fields})
    return {"id": lead_id, "ref": _ref(kind, lead_id)}


def is_bot(data):
    """Honeypot: real people never fill the hidden 'website' field."""
    return bool(clean_text(data.get("website"), 20))


def create_callback(store, data, source="widget"):
    common = _common(data)
    interest = data.get("interest") if data.get("interest") in INTERESTS else "not_sure"
    board = data.get("board") if data.get("board") in BOARDS else ""
    role = data.get("role") if data.get("role") in ROLES else "parent"
    pref = data.get("pref_time") if data.get("pref_time") in PREF_TIMES else "any"
    fields = {**common, "role": role, "board": board, "interest": interest, "pref_time": pref,
              "note": clean_text(data.get("note"), 300), "source": source}
    lead_id = store.add_lead("callback", **fields)
    return _finish(store, "callback", lead_id, fields)


def create_counselling(store, data):
    common = _common(data)
    pref = data.get("pref_time") if data.get("pref_time") in PREF_TIMES else "any"
    fields = {**common, "role": "student", "interest": clean_text(data.get("class_name"), 40), "pref_time": pref,
              "note": clean_text(data.get("note"), 300), "source": "widget-wellness"}
    lead_id = store.add_lead("counselling", **fields)
    return _finish(store, "counselling", lead_id, fields)


# ---------------------------------------------------------------------------------------
# Campus visits
# ---------------------------------------------------------------------------------------
def _visit_cfg():
    import json
    from .. import config
    return json.loads((config.DATA_DIR / "visit_slots.json").read_text(encoding="utf-8"))


def available_slots(store, now=None):
    cfg = _visit_cfg()
    now = now or datetime.now(events.IST)
    earliest = now + timedelta(hours=cfg["min_hours_ahead"])
    days = []
    for offset in range(0, cfg["days_ahead"] + 1):
        day = (now + timedelta(days=offset)).date()
        if day.weekday() not in cfg["weekdays"] or day.isoformat() in cfg["blackout_dates"]:
            continue
        slots = []
        for t in cfg["times"]:
            hh, mm = (int(x) for x in t.split(":"))
            when = datetime(day.year, day.month, day.day, hh, mm, tzinfo=events.IST)
            if when < earliest:
                continue
            left = cfg["capacity"] - store.slot_taken(day.isoformat(), t)
            if left > 0:
                slots.append({"time": t, "left": left})
        if slots:
            days.append({"date": day.isoformat(), "label": day.strftime("%a %d %b"), "slots": slots})
    return {"days": days, "place": cfg["place"], "note": cfg["note"]}


def book_visit(store, data, now=None):
    common = _common(data)
    slot_date, slot_time = clean_text(data.get("date"), 10), clean_text(data.get("time"), 5)
    cfg = _visit_cfg()
    offered = {(d["date"], s["time"]) for d in available_slots(store, now)["days"] for s in d["slots"]}
    if (slot_date, slot_time) not in offered:
        raise ValidationError("slot", "That slot is no longer available. Please pick another")
    interest = data.get("interest") if data.get("interest") in INTERESTS else "not_sure"
    fields = {**common, "role": data.get("role") if data.get("role") in ROLES else "parent", "interest": interest,
              "note": clean_text(data.get("note"), 300), "source": "widget"}
    lead_id = store.book_visit(cfg["capacity"], slot_date, slot_time, **fields)
    if lead_id is None:
        raise ValidationError("slot", "Someone just took the last place in that slot. Please pick another")
    result = _finish(store, "visit", lead_id, {**fields, "slot_date": slot_date, "slot_time": slot_time})
    result.update({"date": slot_date, "time": slot_time, "place": cfg["place"], "note": cfg["note"]})
    return result


__all__ = ["ValidationError", "create_callback", "create_counselling", "available_slots", "book_visit",
           "is_bot", "clean_phone", "StoreError"]
