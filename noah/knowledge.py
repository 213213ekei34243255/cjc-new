"""What Noah knows about the college.

Gemini receives the whole (small) fact sheet on every call, so it never has to guess which snippet is
relevant. Qwen's context is tiny, so it gets only the top few snippets (global_setup.search_memory).
"""

import re

import global_setup
from global_setup import DATA, FEE_NOTE  # noqa: F401  (re-exported for callers)

from . import links as site_links
from .store import StoreError

STREAM_NAMES = {
    "PCMC": "Science - Physics, Chemistry, Maths, Computer Science",
    "PCMB": "Science - Physics, Chemistry, Maths, Biology",
    "CAMS": "Commerce - Accountancy, Maths, Statistics",
    "CAME": "Commerce - Accountancy, Maths, Economics",
    "HESP": "Arts - History, Economics, Sociology, Political Science",
    "HEPP": "Arts - History, Economics, Political Science, Psychology",
    "PPES": "Arts - Political Science, Psychology, Economics, Sociology",
}

# Facts that are not in veronica_memory.json but are published on the live website.
OFFICE_NUMBERS = (
    "Contact numbers: PU office +91 080 4012 9292; IBDP office +91 78921 87650 and +91 080 4012 9298. "
    "Email: office@cjc.christcollege.edu."
)

PRIVACY_NOTE = (
    "Privacy: chat messages are stored for a limited time (90 days by default) and can be read by "
    "authorised college staff to improve answers. Counselling and wellness check-ins are not stored. "
    "Phone numbers shared in a callback or visit request are used only by the college office to contact you."
)


def stream_codes():
    return [c for c in DATA.get("fees", {}) if c != "IBDP"]


def fee_value(code):
    return DATA.get("fees", {}).get(code)


def stream_family(code):
    for family, codes in DATA.get("streams", {}).items():
        if code in codes:
            return family
    return ""


def cutoff_table():
    """{'PCMB': {'SC': 77.12, 'ST': None, 'CAT I': 82.72, ...}} parsed from the published cutoff rules."""
    out = {}
    pair = re.compile(r"(SC|ST|CAT\s+I{1,3}[AB]?|CAT\s+I):\s*(NA|[\d.]+)\s*%?", re.I)
    for rule in DATA.get("rules", []):
        m = re.match(r"\s*([A-Z]{4})\s*-\s*(SC:.*)", rule)
        if not m:
            continue
        code, rest = m.group(1), m.group(2)
        row = {}
        for cat, val in pair.findall(rest):
            row[re.sub(r"\s+", " ", cat.upper())] = None if val.upper() == "NA" else float(val)
        if row:
            out[code] = row
    return out


# ------------------------------------------------------------------------------------------
# Timetable (staff can replace it from the widget; the bundled one is the default)
# ------------------------------------------------------------------------------------------
def get_timetable(store=None):
    if store is not None:
        try:
            custom = store.kv_get("timetable")
            if isinstance(custom, dict) and custom.get("schedule"):
                return custom
        except StoreError:
            pass
    return DATA.get("mid_term_examination_timetable") or {}


def timetable_text(tt):
    lines = []
    for day in tt.get("schedule", []):
        if day.get("subjects"):
            subs = ", ".join(f"{s['name']} (code {s['code']})" for s in day["subjects"])
            lines.append(f"{day['date']} {day['day']}: {subs}, {day.get('timing', tt.get('exam_timing', ''))}")
        else:
            lines.append(f"{day['date']} {day['day']}: {day.get('event', 'Holiday')}")
    return "\n".join(lines)


# ------------------------------------------------------------------------------------------
# The fact sheet
# ------------------------------------------------------------------------------------------
def facts_text(store=None):
    parts = []
    chunks = [c["text"] for c in global_setup.CHUNKS]
    parts.append("CORE FACTS\n" + "\n".join(f"- {t}" for t in chunks))

    adm = DATA.get("admissions", {})
    faq = DATA.get("faq", {})
    parts.append(
        "ADMISSIONS\n"
        f"- {faq.get('admission_status', '')}\n"
        "- PU (1st PUC) admission is online, based on Class 10 marks, with no admission test or interview. "
        "The college takes no donation and uses no agents.\n"
        "- IBDP admission steps: admission test, interview, then fee payment.\n"
        "- A student cannot join 2nd PUC directly; CBSE 12th is not available."
    )
    parts.append(
        "PROGRAMMES\n"
        f"- {DATA.get('definitions', {}).get('puc_full', '')}\n"
        f"- {DATA.get('definitions', {}).get('ibdp_full', '').replace(chr(92) + 'n', ' ')}\n"
        f"- IBDP fee as published: {DATA.get('fees', {}).get('IBDP', 'contact the IBDP office')}. "
        "Ask the IBDP office what each figure covers.\n"
        "- Science stream has no Maths exemption: only PCMC and PCMB are offered. English is compulsory plus one "
        f"second language ({', '.join(DATA.get('languages', [])[1:])}).\n"
        "- Streams: " + "; ".join(f"{c} = {n}" for c, n in STREAM_NAMES.items())
    )
    parts.append(
        "CAMPUS AND LIFE\n"
        "- Location: Dharmaram Campus, Hosur Road, near Koramangala, Bengaluru 560029. "
        f"Access: {', '.join(DATA.get('location', {}).get('access', []))}.\n"
        "- Classes for 1st and 2nd PUC have started for the current year.\n"
        f"- Departments: {', '.join(DATA.get('departments', []))}.\n"
        f"- Campus rules: {', '.join(DATA.get('rules_culture', []))}.\n"
        f"- Extras: {', '.join(DATA.get('student_life', {}).get('extras', []))}."
    )
    parts.append("CONTACT\n- " + OFFICE_NUMBERS)

    tt = get_timetable(store)
    if tt.get("schedule"):
        parts.append(f"EXAM TIMETABLE - {tt.get('title', '')}, {tt.get('term', '')}, {tt.get('course', '')}\n"
                     + timetable_text(tt))

    if store is not None:
        try:
            from .features import events as events_feature      # imported here: events -> store, knowledge -> events
            events_feature.seed(store)
            events = store.list_events()
            if events:
                parts.append("EVENTS AND CAMPAIGNS\n" + "\n".join(
                    f"- {e['title']}: {e['blurb']}" + (f" Starts {e['starts']}." if e["starts"] else " Dates not announced yet.")
                    + (f" Link: {e['link_url']}" if e["link_url"] else "") for e in events))
            learned = store.list_learned()
            if learned:
                parts.append("STAFF-APPROVED ANSWERS (these override anything above)\n" + "\n".join(
                    f"- Q: {l['question']}\n  A: {l['answer']}" for l in learned))
        except StoreError:
            pass

    parts.append("PRIVACY\n- " + PRIVACY_NOTE)
    parts.append("WEBSITE PAGES (you may mention these)\n" + "\n".join(
        f"- {label.replace('Open ', '')}: {url}" for label, url in site_links.PAGES.values()))
    return "\n\n".join(parts)


def qwen_context(query, store=None):
    """Small context for the 1.5B backup model: top snippets plus any staff-approved answers."""
    hits = [c["text"] for c in global_setup.search_memory(query, top_k=6)]
    extra = []
    if store is not None:
        try:
            extra = [f"Q: {l['question']} A: {l['answer']}" for l in store.list_learned()][:6]
        except StoreError:
            pass
    return "\n".join(hits + extra)


# ------------------------------------------------------------------------------------------
# Fee sanity check applied to every model answer
# ------------------------------------------------------------------------------------------
_AMOUNT = re.compile(r"(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d+)?)\s*(lakhs?|l\b|k\b)?", re.I)


def _to_number(raw, unit):
    value = float(raw.replace(",", ""))
    unit = (unit or "").lower()
    if unit.startswith("l"):
        value *= 100000
    elif unit == "k":
        value *= 1000
    return round(value)


def known_amounts(store=None):
    known = set()
    for v in DATA.get("fees", {}).values():
        if isinstance(v, int):
            known.add(v)
        elif isinstance(v, str):
            for raw, unit in re.findall(r"([\d.]+)\s*(L|lakh|k)?", v, re.I):
                if raw.replace(".", "").isdigit():
                    known.add(_to_number(raw, unit))
    if store is not None:
        try:
            for l in store.list_learned():
                for raw, unit in _AMOUNT.findall(l["answer"]):
                    known.add(_to_number(raw, unit))
        except StoreError:
            pass
    return known


def fee_numbers_consistent(answer, store=None):
    mentioned = [_to_number(raw, unit) for raw, unit in _AMOUNT.findall(answer or "")]
    if not mentioned:
        return True
    known = known_amounts(store)
    return all(m in known for m in mentioned)
