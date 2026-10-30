"""Feature 11 - Student Zone: access-code login and the personal exam planner.

Honest limit: this is NOT a login to the college's own Student Login portal (that system is separate
and not connected). Staff issue access codes from the staff panel inside the widget; a code opens the
Student Zone for one class and can be revoked at any time.
"""

from datetime import datetime

from .. import auth, knowledge
from ..store import StoreError
from . import events


def login(store, code):
    row = store.verify_student_code(code)
    if not row:
        return None
    return {"token": auth.student_token(row), "label": row["label"], "course": row.get("course", "")}


def _parse_day(text):
    try:
        return datetime.strptime(text, "%d.%m.%Y").date()
    except (TypeError, ValueError):
        return None


def all_subjects(tt):
    seen = []
    for day in tt.get("schedule", []):
        for s in day.get("subjects", []):
            if s["name"] not in seen:
                seen.append(s["name"])
    return sorted(seen)


def exam_plan(tt, subjects, now=None):
    """Personal exam list for the chosen subjects, with the next exam and days left."""
    now = now or datetime.now(events.IST)
    today = now.date()
    chosen = {s.lower() for s in (subjects or [])}
    rows, next_exam = [], None
    for day in tt.get("schedule", []):
        d = _parse_day(day.get("date"))
        if not d:
            continue
        if not day.get("subjects"):
            rows.append({"date": d.isoformat(), "day": day.get("day", ""), "holiday": day.get("event", "Holiday"),
                         "subjects": [], "timing": "", "days_left": (d - today).days})
            continue
        mine = [s for s in day["subjects"] if not chosen or s["name"].lower() in chosen]
        if not mine:
            continue
        item = {"date": d.isoformat(), "day": day.get("day", ""), "subjects": mine,
                "timing": day.get("timing", tt.get("exam_timing", "")), "holiday": None, "days_left": (d - today).days}
        rows.append(item)
        if item["days_left"] >= 0 and next_exam is None:
            next_exam = item
    exam_rows = [r for r in rows if r["subjects"]]
    return {
        "title": tt.get("title", "Exam timetable"), "term": tt.get("term", ""), "course": tt.get("course", ""),
        "timing": tt.get("exam_timing", ""), "rows": rows, "next": next_exam,
        "finished": bool(exam_rows) and next_exam is None,
        "subjects": all_subjects(tt),
    }


def timetable_for(store):
    return knowledge.get_timetable(store)


def validate_timetable(obj):
    """Staff paste JSON into the widget; make sure it is usable before it replaces the bundled one."""
    if not isinstance(obj, dict) or not isinstance(obj.get("schedule"), list) or not obj["schedule"]:
        raise ValueError("timetable needs a non-empty 'schedule' list")
    for day in obj["schedule"]:
        if not isinstance(day, dict) or not _parse_day(day.get("date")):
            raise ValueError("every day needs a date like 28.09.2026")
        for s in day.get("subjects", []) or []:
            if not isinstance(s, dict) or not s.get("name"):
                raise ValueError("every subject needs a name")
    return {k: obj.get(k, "") for k in ("title", "academic_year", "term", "course", "exam_timing")} | {"schedule": obj["schedule"]}


__all__ = ["login", "exam_plan", "all_subjects", "timetable_for", "validate_timetable", "StoreError"]
