"""Feature 1 - Stream advisor and the PU vs IBDP comparison.

Pure rules, no LLM: the same answers always give the same ranking, and nothing can be invented.
The weights below are a guidance heuristic written for this project - they are NOT college policy
and the result card says so. Fees and cutoffs come straight from veronica_memory.json.
"""

from .. import knowledge

CATEGORIES = ["SC", "ST", "CAT I", "CAT IIA", "CAT IIB", "CAT IIIA", "CAT IIIB"]

QUESTIONS = [
    {"id": "board", "type": "choice", "title": "Which board is your Class 10 from?",
     "options": [{"id": "state", "label": "Karnataka State"}, {"id": "cbse", "label": "CBSE"},
                 {"id": "icse", "label": "ICSE"}, {"id": "other", "label": "IGCSE / other"}]},
    {"id": "percent", "type": "slider", "title": "Your overall Class 10 percentage", "min": 35, "max": 100, "default": 75, "unit": "%"},
    {"id": "maths", "type": "slider", "title": "Your Maths marks", "min": 20, "max": 100, "default": 70, "unit": "%", "optional": True},
    {"id": "science", "type": "slider", "title": "Your Science marks", "min": 20, "max": 100, "default": 70, "unit": "%", "optional": True},
    {"id": "category", "type": "choice", "title": "Admission category (optional)", "optional": True,
     "hint": "Used only to compare with the published cutoffs.",
     "options": [{"id": "", "label": "Skip"}] + [{"id": c, "label": c} for c in CATEGORIES]},
    {"id": "interests", "type": "multi", "title": "What excites you most? Pick up to 3", "max": 3,
     "options": [{"id": "tech", "label": "Coding and computers"}, {"id": "bio", "label": "Biology and health"},
                 {"id": "eng", "label": "Physics and building things"}, {"id": "fin", "label": "Money, business, accounts"},
                 {"id": "hum", "label": "History, society, politics"}, {"id": "psy", "label": "Understanding people"},
                 {"id": "law", "label": "Law, debate, public service"}, {"id": "global", "label": "Global, project-based learning"}]},
    {"id": "goal", "type": "choice", "title": "Where do you see yourself after school?",
     "options": [{"id": "engineer", "label": "Engineer or technologist"}, {"id": "doctor", "label": "Doctor or health professional"},
                 {"id": "finance", "label": "CA, finance or business"}, {"id": "law", "label": "Lawyer or civil services"},
                 {"id": "psych", "label": "Psychologist or social scientist"}, {"id": "undecided", "label": "Not sure yet"}]},
    {"id": "style", "type": "choice", "title": "How do you like to learn?",
     "options": [{"id": "structured", "label": "Clear syllabus, regular exams"}, {"id": "inquiry", "label": "Projects, research and discussion"},
                 {"id": "mixed", "label": "A bit of both"}]},
]

# interest / goal / style -> stream points
_INTEREST = {
    "tech": {"PCMC": 3}, "bio": {"PCMB": 3}, "eng": {"PCMC": 3, "PCMB": 1},
    "fin": {"CAMS": 3, "CAME": 3}, "hum": {"HESP": 3, "HEPP": 2, "PPES": 2},
    "psy": {"HEPP": 3, "PPES": 3}, "law": {"HESP": 2, "HEPP": 2, "PPES": 2},
    "global": {"IBDP": 3},
}
_GOAL = {
    "engineer": {"PCMC": 3, "PCMB": 1}, "doctor": {"PCMB": 4}, "finance": {"CAMS": 3, "CAME": 3},
    "law": {"HESP": 2, "HEPP": 2, "PPES": 2}, "psych": {"HEPP": 3, "PPES": 3}, "undecided": {},
}
_STYLE = {"structured": {}, "inquiry": {"IBDP": 3}, "mixed": {"IBDP": 1}}

_REASONS = {
    "PCMC": "Physics, Chemistry, Maths and Computer Science - the usual route to engineering and computing.",
    "PCMB": "Physics, Chemistry, Maths and Biology - keeps both medicine and engineering open.",
    "CAMS": "Accountancy, Maths and Statistics - suits CA, analytics and finance.",
    "CAME": "Accountancy, Maths and Economics - suits CA, business and economics.",
    "HESP": "History, Economics, Sociology and Political Science - society, policy, law and civil services.",
    "HEPP": "History, Economics, Political Science and Psychology - people, policy and law.",
    "PPES": "Political Science, Psychology, Economics and Sociology - psychology and social sciences.",
    "IBDP": "Six subjects at Higher or Standard Level plus TOK, CAS and an Extended Essay - inquiry-based and global.",
}


def _num(answers, key, default=None):
    try:
        return float(answers.get(key))
    except (TypeError, ValueError):
        return default


def recommend(answers):
    """answers -> ranked list. Raises ValueError on unusable input."""
    percent = _num(answers, "percent")
    if percent is None or not 0 <= percent <= 100:
        raise ValueError("percent must be between 0 and 100")
    maths = _num(answers, "maths")
    science = _num(answers, "science")
    category = (answers.get("category") or "").upper().strip()
    interests = [i for i in (answers.get("interests") or []) if i in _INTEREST][:3]
    goal = answers.get("goal") if answers.get("goal") in _GOAL else "undecided"
    style = answers.get("style") if answers.get("style") in _STYLE else "structured"

    codes = knowledge.stream_codes()
    raw = {c: 0.0 for c in codes + ["IBDP"]}
    why = {c: [] for c in raw}

    for i in interests:
        for code, pts in _INTEREST[i].items():
            raw[code] += pts
            why[code].append("matches your interest" if i != "global" else "you like global, project-based learning")
    for code, pts in _GOAL[goal].items():
        raw[code] += pts
        why[code].append("fits your goal")
    for code, pts in _STYLE[style].items():
        raw[code] += pts
        if code == "IBDP":
            why[code].append("you prefer projects and research")

    warnings = {c: [] for c in raw}
    if maths is not None:
        for code in ("PCMC", "PCMB"):
            if maths < 50:
                raw[code] -= 4
                warnings[code].append("Maths is a core subject here and your score is low - plan extra support")
            elif maths < 60:
                raw[code] -= 2
                warnings[code].append("Maths is demanding in this stream")
            elif maths >= 80:
                raw[code] += 1
                why[code].append("strong Maths score")
        for code in ("CAMS", "CAME"):
            if maths < 45:
                raw[code] -= 1
                warnings[code].append("this stream includes Maths")
    if science is not None and science >= 70:
        raw["PCMB"] += 1
        raw["PCMC"] += 1
        why["PCMB"].append("good Science score")
        why["PCMC"].append("good Science score")

    cutoffs = knowledge.cutoff_table()
    results = []
    for code, score in raw.items():
        fit = int(max(5, min(98, 45 + score * 7)))
        entry = {
            "code": code,
            "name": knowledge.STREAM_NAMES.get(code, "IB Diploma Programme" if code == "IBDP" else code),
            "family": "IBDP" if code == "IBDP" else knowledge.stream_family(code),
            "fit": fit,
            "fee": knowledge.fee_value(code),
            "reasons": why[code][:3] or ["no strong signal either way"],
            "warnings": warnings[code],
            "blurb": _REASONS.get(code, ""),
            "cutoff": None,
        }
        if code == "IBDP":
            entry["fee_note"] = "As published. Ask the IBDP office what each figure covers."
            entry["process"] = "Admission test, interview, then fee."
        elif category and code in cutoffs:
            value = cutoffs[code].get(category)
            if value is None:
                entry["cutoff"] = {"category": category, "value": None, "status": "not_published"}
            else:
                entry["cutoff"] = {"category": category, "value": value,
                                   "status": "above" if percent >= value else "below"}
        results.append(entry)

    results.sort(key=lambda r: (-r["fit"], r["code"]))
    top = results[:3]
    # Always surface IBDP when the student asked for it, even if three PU streams scored higher.
    if "IBDP" not in [r["code"] for r in top] and (style == "inquiry" or "global" in interests):
        top = top[:2] + [next(r for r in results if r["code"] == "IBDP")]
    return {
        "results": top,
        "admission_status": knowledge.DATA.get("faq", {}).get("admission_status", ""),
        "disclaimer": ("This is a guide based on your answers, not an eligibility decision. Admission follows the "
                       "college's own selection process. Cutoffs shown are the published ones; confirm with the office."),
    }


def compare():
    d = knowledge.DATA
    fees = d.get("fees", {})
    pu_fees = [v for k, v in fees.items() if k != "IBDP" and isinstance(v, int)]
    return {
        "columns": ["Pre-University (PU)", "IB Diploma (IBDP)"],
        "rows": [
            ["Duration", "2 years (1st and 2nd PUC)", "2 years"],
            ["Board", "Karnataka Pre-University Board", "International Baccalaureate"],
            ["Subjects", "A fixed stream: Science, Commerce or Arts", "Six subjects (3+ Higher Level) plus TOK, CAS and Extended Essay"],
            ["Selection", "Class 10 marks. No test or interview", "Admission test, interview, then fee"],
            ["Fees (per year)", f"Rs {min(pu_fees):,} to Rs {max(pu_fees):,} depending on stream", f"{fees.get('IBDP', 'Ask the IBDP office')} (as published)"],
            ["Applications now", "Closed", "Open"],
        ],
        "note": "PU and IBDP have separate fees and processes. They are never combined.",
    }
