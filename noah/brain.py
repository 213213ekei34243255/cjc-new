"""Noah's brain: turns one visitor message into one reply.

Pipeline (first match wins):
  1. crisis safety net (every mode, every language)      -> fixed helpline reply, never logged
  2. "open <page>" / pasted link
  3. tool intents (advisor, callback, visit, documents, careers, events, wellness, student, study)
  4. deterministic facts (fees, contact, leadership, hostel, board ...)   -> zero hallucination risk
  5. staff-taught answers
  6. off-topic guard
  7. answer cache (first question of a session)
  8. LLM: Gemini with the full fact sheet, Qwen as backup

`prepare()` runs steps 1-7 and either returns a finished Reply or a Plan for the LLM. `respond()` and
`respond_stream()` execute a Plan; the streaming endpoint shows words as they arrive.
"""

import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from . import config, knowledge, llm, sessions
from . import links as site_links
from .features import advisor, events as events_feature, wellness
from .lang import LANGS, lang_name, resolve_lang
from .store import StoreError, get_store, normalize

log = logging.getLogger("noah.brain")

# Set by app.py so exchanges are also written to the legacy Postgres log. Called as sink(sid, role, text, reply_id, url, ua).
legacy_sink = None

_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

# ------------------------------------------------------------------------------------------------
# Prompts
# ------------------------------------------------------------------------------------------------
IDENTITY = """You are Noah, the official AI assistant for Christ Junior College (CJC), Bengaluru.
IDENTITY - follow exactly:
- Your name is Noah. You were created by CogniAI Studios. Your architecture/model is Rexy-1.
- Abraham Shaun Sunil is the creator/founder associated with your development.
- You were NOT created by Anthropic, OpenAI, Google, Meta, or any other AI company. Never name any underlying model or vendor.
- If asked "Who made you?" answer: "I was created by CogniAI Studios." If asked "What model are you?" answer: "My architecture is Rexy-1."
- Never invent or speculate about your identity, creator, architecture, or organisation.
HARD RULES:
- Only introduce yourself if the user asks who you are.
- Answer only what is asked. Stay within Christ Junior College topics (admissions, fees, streams, cutoffs, events, facilities, contact, policies, student life, exams).
- Unrelated topics (sports, celebrities, entertainment, politics, personal opinions): decline in ONE short sentence and redirect to college topics. Do not answer first.
- Keep answers short: usually 2-4 sentences (about 50-100 words). Use a short list only when the user asks for a list.
- Never invent information. If the facts do not contain the answer, say so plainly and suggest the admissions office.
- All fees are annual. There is no monthly fee plan. Never state or imply a monthly figure, and never add up or estimate totals.
- Never mix PU (Pre-University) and IBDP fees or processes in one answer unless the user asks to compare them.
- This is a Karnataka State Board PUC college (1st and 2nd PUC). It is NOT an ICSE or CBSE school. For those boards point to the sister schools: ICSE https://christschool.info/ , CBSE https://christschool.edu.in/ , Karnataka State https://christschoolblr.in/
- Christ Junior College is a Christian institution open to students of all religions. Never describe it as being "for" one religion.
- Never mention internal details: no JSON keys, "knowledge base", "context", "facts", "sheet" or how you found something. Just state the answer.
- Admission status changes: use the facts below, and say the admissions office confirms the latest.
FORMAT: plain text. You may use **bold** for key figures and "- " bullets. No headings, tables or emoji.
MARKERS (machine-read, never explain them):
- If the facts do not contain the answer, START your reply with [[UNKNOWN]] and then answer honestly (for example: you do not have that detail and the office can help).
- If the user seems to be in danger or talks about harming themselves, reply with ONLY [[CRISIS]] .
- If a tool would help, END your reply with one marker: [[OPEN:advisor]] (choose a stream), [[OPEN:callback]] (talk to admissions),
  [[OPEN:visit]] (book a campus visit), [[OPEN:documents]] (document checklist), [[OPEN:careers]] (career paths),
  [[OPEN:events]] (events), [[OPEN:wellness]] (feeling stressed or low), [[OPEN:compare]] (PU vs IBDP)."""

QWEN_TAIL = "\nKeep the answer to 2-4 sentences. Use ONLY the facts given. If the facts do not contain the answer, say you do not have it and suggest contacting the admissions office."

LANG_RULE = "Reply in {name}. Keep names, numbers, course codes and links as they are."

OFF_TOPIC_WORDS = [
    "world cup", "goat of football", "footballer", "messi", "ronaldo", "actor", "actress", "movie", "film",
    "dinosaur", "dna", "genetic engineering", "flight simulator", "who is the president", "girlfriend",
    "boyfriend", "hey babe", "personal opinion",
]
_OFF_TOPIC = re.compile(r"\b(" + "|".join(re.escape(w) for w in OFF_TOPIC_WORDS) + r")\b", re.I)
OFF_TOPIC_REPLY = ("I'm Noah, and I'm only set up to help with Christ Junior College topics like admissions, "
                   "fees, streams, and campus life. Happy to help with any of those!")

# ------------------------------------------------------------------------------------------------
# Data classes
# ------------------------------------------------------------------------------------------------


@dataclass
class Ctx:
    text: str
    sid: str
    url: str = ""
    lang_pref: str = "en"
    student: dict | None = None
    mode: str = "chat"            # "chat" | "study"
    ip: str = ""
    user_agent: str = ""
    channel: str = "web"          # "web" | "whatsapp"


@dataclass
class Reply:
    answer: str
    intent: str = "llm"
    engine: str = "rules"
    lang: str = "en"
    cards: list = field(default_factory=list)
    chips: list = field(default_factory=list)
    actions: list = field(default_factory=list)
    links: list = field(default_factory=list)
    url: str | None = None
    private: bool = False
    unknown: bool = False
    reply_id: str = ""
    translate: bool = False       # canned English text that should be translated for non-English visitors

    def to_dict(self):
        out = {
            "answer": self.answer, "reply_id": self.reply_id, "intent": self.intent, "engine": self.engine,
            "lang": self.lang, "cards": self.cards, "chips": self.chips, "actions": self.actions,
            "links": self.links, "private": self.private,
        }
        if self.url:
            out["url"] = self.url
        return out


@dataclass
class Plan:
    ctx: Ctx
    lang: str
    system: str
    messages: list
    qwen_system: str
    cache_key: str | None = None
    study: bool = False


# ------------------------------------------------------------------------------------------------
# Chips (suggested next messages) and cards
# ------------------------------------------------------------------------------------------------
def _chip(label, send=None, open_=None):
    c = {"label": label}
    if send:
        c["send"] = send
    if open_:
        c["open"] = open_
    return c


CHIPS = {
    "fees": [_chip("Compare PU and IBDP", open_="compare"), _chip("Which stream suits me?", open_="advisor"), _chip("Book a campus visit", open_="visit")],
    "admission": [_chip("Documents needed", open_="documents"), _chip("Talk to admissions", open_="callback"), _chip("Book a campus visit", open_="visit")],
    "contact": [_chip("Book a campus visit", open_="visit"), _chip("Request a callback", open_="callback")],
    "default": [_chip("Fees", send="What are the fees?"), _chip("Which stream suits me?", open_="advisor"), _chip("Talk to admissions", open_="callback")],
    "unknown": [_chip("Talk to admissions", open_="callback"), _chip("Contact details", send="How do I contact the college?")],
    "student": [_chip("My exams", open_="student"), _chip("Quiz me", open_="study")],
}


def contact_card():
    faq = knowledge.DATA.get("faq", {})
    contact = faq.get("contact", {})
    maps = "https://www.google.com/maps/search/?api=1&query=Christ+Junior+College+Dharmaram+Campus+Hosur+Road+Bengaluru"
    return {
        "type": "contact", "title": "Contact Christ Junior College",
        "rows": [
            {"label": "PU office", "value": contact.get("phone", ""), "href": "tel:" + re.sub(r"[^\d+]", "", contact.get("phone", ""))},
            {"label": "IBDP office", "value": "+91 78921 87650", "href": "tel:+917892187650"},
            {"label": "Email", "value": contact.get("email", ""), "href": "mailto:" + contact.get("email", "")},
            {"label": "Address", "value": "Dharmaram Campus, Hosur Road, near Koramangala, Bengaluru 560029", "href": maps},
            {"label": "Office hours", "value": faq.get("timings", {}).get("office", "")},
        ],
        "buttons": [{"label": "Get directions", "url": maps}],
    }


def fee_card(codes=None, title="Annual fees"):
    fees = knowledge.DATA.get("fees", {})
    rows = []
    for code in codes or list(fees):
        v = fees.get(code)
        if v is None:
            continue
        name = knowledge.STREAM_NAMES.get(code, "IB Diploma Programme" if code == "IBDP" else code)
        rows.append({"code": code, "name": name, "value": f"Rs {v:,}" if isinstance(v, int) else str(v)})
    return {"type": "fees", "title": title, "rows": rows, "note": "All fees are per academic year, not monthly."}


# ------------------------------------------------------------------------------------------------
# Deterministic handlers (answers that must never be improvised)
# ------------------------------------------------------------------------------------------------
_FEE_WORDS = re.compile(r"\b(fee|fees|cost|costs|price|tuition|charges?|payment|pay|how much|amount|rupees|rs)\b", re.I)


def handle_fee_query(q):
    if not _FEE_WORDS.search(q) and not re.search(r"monthly", q, re.I):
        return None
    data = knowledge.DATA
    fees, mappings = data.get("fees", {}), data.get("mappings", {})
    ql = q.lower()
    for code, fee in fees.items():
        if re.search(rf"\b{code.lower()}\b", ql):
            if code == "IBDP":
                return Reply(f"The IBDP fee is published as {fee} for the academic year. Please confirm with the IBDP office what each figure covers.",
                             intent="fees", cards=[fee_card(["IBDP"], "IBDP fee")], translate=True)
            return Reply(f"{code} fee is ₹{fee:,} for the full academic year (not monthly).", intent="fees",
                         cards=[fee_card([code], f"{code} annual fee")], translate=True)
    for key, codes in mappings.items():
        if re.search(rf"\b{re.escape(key)}\b", ql):
            parts = [f"{c} ₹{fees[c]:,}/year" for c in codes if c in fees]
            return Reply(f"Fees for {key.title()}: " + ", ".join(parts) + ". All figures are annual.", intent="fees",
                         cards=[fee_card([c for c in codes if c in fees], f"{key.title()} fees")], translate=True)
    if re.search(r"\bibdp?\b|\bib\b", ql):
        return handle_fee_query("ibdp fee")
    if re.search(r"\bclass\s*1[12](th)?\b|\b1st\s*puc\b|\b2nd\s*puc\b|\bmonthly\b|\b11th\b|\b12th\b|\bpuc?\b|\bfees?\b", ql):
        all_fees = ", ".join(f"{c} ₹{v:,}/year" for c, v in fees.items() if c != "IBDP")
        return Reply(f"Fees depend on the stream you choose (all annual, not monthly): {all_fees}. Tell me your stream and I'll give the exact figure.",
                     intent="fees", cards=[fee_card([c for c in fees if c != "IBDP"], "PU fees by stream")], translate=True)
    return None


def handle_misc(q):
    ql = q.lower()
    data = knowledge.DATA
    if re.search(r"\b(hindu|muslim|religion|christian only)\b", ql):
        return Reply("Christ Junior College is a Christian institution affiliated with Christ University, but admission is open to students of all religions and backgrounds.",
                     intent="affiliation", translate=True)
    if re.search(r"\b(icse|cbse|state board|which board|what board)\b", ql):
        return Reply("Christ Junior College is a Karnataka State Board Pre-University college offering 1st PUC and 2nd PUC. It is not an ICSE or CBSE college. "
                     "For those boards please see the sister schools: ICSE https://christschool.info/ , CBSE https://christschool.edu.in/ , Karnataka State https://christschoolblr.in/",
                     intent="board", translate=True)
    if re.search(r"\bhostel\b", ql):
        return Reply(data["faq"]["hostel"] + ".", intent="hostel", translate=True)
    lead = data.get("leadership", {})
    if re.search(r"\bvice[\s-]?principal\b", ql):
        return Reply(f"The Vice Principal is {lead.get('vice_principal')}.", intent="leadership", translate=True)
    if re.search(r"\bprincipal\b", ql):
        return Reply(f"The Principal of Christ Junior College is {lead.get('principal')}.", intent="leadership", translate=True)
    if re.search(r"\badmissions?\b", ql) and re.search(r"\b(status|open|closed|close|still)\b", ql):
        return Reply(data["faq"]["admission_status"], intent="admission", chips=CHIPS["admission"], translate=True)
    if re.search(r"\b(contact|phone number|call the college|email|address|where is|location|directions?|map|reach)\b", ql):
        return Reply("Here are the ways to reach the college.", intent="contact", cards=[contact_card()], chips=CHIPS["contact"], translate=True)
    return None


# ------------------------------------------------------------------------------------------------
# Tool intents
# ------------------------------------------------------------------------------------------------
def _open(panel, **args):
    return {"open": panel, **({"args": args} if args else {})}


_RX = {
    "wellness": re.compile(r"\b(stress(ed)?|anxious|anxiety|depress\w*|overwhelm\w*|burn(ed|t)?[\s-]?out|lonely|panic|"
                           r"counsel(l)?(ing|or|lor)|wellness|mental health|feeling low|feel low|can'?t sleep|"
                           r"exam (fear|pressure)|worried about (my )?exams?)\b", re.I),
    "advisor": re.compile(r"((which|what|suggest|recommend|choose|pick|best|right)\b.{0,40}\b(stream|combination|course)\b)|"
                          r"\bstream (advisor|selector|quiz|finder)\b|help me (choose|pick|decide)", re.I),
    "compare": re.compile(r"\b(pu|puc|pre[\s-]?university)\b.{0,30}\b(vs|versus|or|compare|difference|better)\b.{0,30}\bib(dp)?\b|"
                          r"\bib(dp)?\b.{0,30}\b(vs|versus|compare|difference|better)\b|\bcompare\b.{0,20}\b(pu|ibdp?)\b", re.I),
    "callback": re.compile(r"(call me|call back|callback|request a call|contact me|"
                           r"(talk|speak|connect|chat)\s+(to|with)\s+(a |an |the )?(someone|person|human|admission\w*|office|counsellor|staff|team))", re.I),
    "visit": re.compile(r"\b(visit|campus tour|tour of|see the campus|book a (slot|visit|tour)|come to (see|visit))\b", re.I),
    "documents": re.compile(r"(\b(documents?|certificates?|papers|checklist)\b.{0,40}\b(need|needed|required|bring|submit|carry|list|apply)\b|"
                            r"\bwhat (to|should i) bring\b|\bdocument list\b|\brequired documents?\b|\bdocuments? (for|required)\b)", re.I),
    "careers": re.compile(r"(\bcareers?\b|\bafter (12th|2nd puc|puc|pcmb|pcmc|commerce|arts|science)\b|\bscope of\b|"
                          r"\bwhat can i do after\b|\b(neet|jee|kcet|cuet|clat)\b)", re.I),
    # Generic words only: a question about one named event ("tell me about CJC MUN") is answered by the model.
    "events": re.compile(r"\b(events?|fests?|upcoming|happening|what'?s on)\b", re.I),
    "student": re.compile(r"\b(student zone|student mode|my exams?|my next exam|next exam|my timetable)\b", re.I),
    "study": re.compile(r"\b(quiz me|flash ?cards?|practice (questions|quiz)|test me|revision help)\b", re.I),
}


def _stream_in(text):
    for code in knowledge.stream_codes() + ["IBDP"]:
        if re.search(rf"\b{code}\b", text, re.I):
            return code
    for kw, code in (("neet", "PCMB"), ("jee", "PCMC"), ("clat", "HESP")):
        if re.search(rf"\b{kw}\b", text, re.I):
            return code
    return None


def handle_tools(ctx, lang):
    q = ctx.text
    if q.strip().lower() in ("/staff", "staff login", "staff mode"):
        return Reply("Opening the staff panel.", intent="tool:staff", actions=[_open("staff")], translate=False)
    if _RX["study"].search(q):
        if ctx.student:
            return Reply("Let's practise. Pick a subject and topic and I'll make you a quiz or flashcards.", intent="tool:study",
                         actions=[_open("study")], translate=True)
        return Reply("The study tools are in the Student Zone. Open it and enter the access code your class teacher gave you.",
                     intent="tool:study", actions=[_open("student")], translate=True)
    if _RX["student"].search(q):
        msg = ("Here is your exam planner." if ctx.student else
               "The Student Zone shows your personal exam planner. Enter the access code from your class teacher to open it.")
        return Reply(msg, intent="tool:student", actions=[_open("student")], translate=True)
    if _RX["wellness"].search(q) and config.WELLNESS_ENABLED:
        return Reply("Thank you for telling me. It is okay to feel this way. I've opened a short, private check-in with a breathing exercise "
                     "and a way to talk to a counsellor. Nothing you do there is saved to the chat log.",
                     intent="tool:wellness", actions=[_open("wellness")], private=True, translate=True)
    if _RX["compare"].search(q):
        return Reply("Here is how the Pre-University course and the IB Diploma compare.", intent="tool:compare",
                     actions=[_open("compare")], chips=CHIPS["fees"], translate=True)
    if _RX["advisor"].search(q):
        return Reply("I can match you to a stream in about a minute. I've opened the Stream Advisor - answer a few quick questions.",
                     intent="tool:advisor", actions=[_open("advisor")], translate=True)
    if _RX["callback"].search(q):
        return Reply("Happy to arrange that. Share your details and the admissions office will call you back.",
                     intent="tool:callback", actions=[_open("callback")], translate=True)
    if _RX["visit"].search(q):
        return Reply("You can book a campus visit slot right here. Pick a day and time that suits you.", intent="tool:visit",
                     actions=[_open("visit")], translate=True)
    if _RX["documents"].search(q):
        return Reply("For 1st PUC you need your Class X marks statement and hall ticket, a TC copy, Aadhaar copy and PEN. "
                     "ICSE, CBSE and other-board students also need a Consumer Number for the Provisional Eligibility Certificate. "
                     "I've opened a checklist you can tick off and save as a PDF.",
                     intent="tool:documents", actions=[_open("documents")], chips=CHIPS["admission"], translate=True)
    if _RX["careers"].search(q):
        code = _stream_in(q)
        return Reply("Here are the paths each stream can lead to. Tap a stream to explore exams, courses and careers.",
                     intent="tool:careers", actions=[_open("careers", path=code) if code else _open("careers")], translate=True)
    if _RX["events"].search(q):
        return Reply("Here are the college events and campaigns. You can open each one for dates, links and reminders.",
                     intent="tool:events", actions=[_open("events")], translate=True)
    return None


# ------------------------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------------------------
def clean_input(text):
    return _CTRL.sub("", str(text or "")).strip()[: config.MAX_MESSAGE_CHARS]


def _crisis_reply(lang):
    c = wellness.crisis_payload()
    return Reply(c["answer"], intent="crisis", private=True, lang=lang, translate=True,
                 cards=[{"type": "helplines", "title": "Talk to someone now", "rows": c["helplines"], "note": c["college_line"]}],
                 chips=[_chip("Talk to a counsellor", open_="wellness")], actions=[_open("wellness")])


def strip_internal_labels(text):
    return re.sub(r"\b\w+\[\d+\]", "", text)


def enforce_length(text, max_sentences=4):
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if s]
    return " ".join(sentences[:max_sentences]).strip()


_MARKER = re.compile(r"\[\[\s*(UNKNOWN|CRISIS|OPEN\s*:\s*([a-z]+))\s*\]\]", re.I)
_PANELS = {"advisor", "callback", "visit", "documents", "careers", "events", "wellness", "compare"}


def _extract_markers(text):
    unknown = crisis = False
    opens = []
    for m in _MARKER.finditer(text):
        tag = m.group(1).upper()
        if tag == "UNKNOWN":
            unknown = True
        elif tag == "CRISIS":
            crisis = True
        elif m.group(2).lower() in _PANELS:
            opens.append(m.group(2).lower())
    cleaned = _MARKER.sub("", text)
    cleaned = re.sub(r"\[\[[^\]]*$", "", cleaned)          # dangling marker from a cut-off stream
    return cleaned.strip(), unknown, crisis, opens


def _translate(texts, lang):
    """Translate short canned strings with the LLM. Returns None when no model can do it."""
    if lang == "en" or not texts:
        return None
    system = (f"Translate each string in the JSON array into {lang_name(lang)}. Keep numbers, rupee amounts, course codes "
              "(PCMB, PCMC, CAMS, CAME, HESP, HEPP, PPES, IBDP), phone numbers, emails and links unchanged. "
              'Return ONLY JSON: {"t": [..same number of strings..]}.')
    try:
        import json
        res = llm.generate(system, [{"role": "user", "content": json.dumps(texts, ensure_ascii=False)}],
                           json_mode=True, max_tokens=900, temperature=0.1, allow_qwen=False)
        out = llm.parse_json(res.text).get("t")
        if isinstance(out, list) and len(out) == len(texts) and all(isinstance(x, str) for x in out):
            return out
    except (llm.LLMError, ValueError, AttributeError):
        pass
    return None


def localize(reply, lang):
    """Translate a canned reply (answer + chip labels) for non-English visitors; falls back to English."""
    reply.lang = lang
    if lang == "en" or not reply.translate:
        return reply
    labels = [c["label"] for c in reply.chips]
    out = _translate([reply.answer] + labels, lang)
    if out:
        reply.answer = out[0]
        for chip, label in zip(reply.chips, out[1:]):
            chip["label"] = label
    return reply


# ------------------------------------------------------------------------------------------------
# prepare / finish
# ------------------------------------------------------------------------------------------------
def _today():
    now = datetime.now(events_feature.IST)
    return now.strftime("%A, %d %B %Y")


def _system_prompt(ctx, lang, store):
    parts = [IDENTITY, f"Today is {_today()} (India)."]
    parts.append(LANG_RULE.format(name=lang_name(lang)) if lang != "en" else
                 "Reply in the language the user writes in (English by default).")
    if ctx.url:
        parts.append(f"The visitor is currently reading this page of the college website: {ctx.url[:200]}")
    parts.append("FACTS ABOUT THE COLLEGE (the only source for college claims):\n" + knowledge.facts_text(store))
    return "\n\n".join(parts)


def _history_messages(sid, mode):
    return [{"role": h["role"], "content": h["text"]} for h in sessions.load_history(sid, mode, limit=6)]


def _learned_match(text, store):
    q = set(normalize(text).split())
    if len(q) < 2:
        return None
    best, best_score = None, 0.0
    try:
        for item in store.list_learned():
            k = set(item["norm"].split())
            if not k:
                continue
            score = len(q & k) / len(q | k)
            if score > best_score:
                best, best_score = item, score
    except StoreError:
        return None
    return best if best and best_score >= 0.8 else None


def prepare(ctx, store=None):
    """Steps 1-7. Returns a finished Reply, or a Plan that needs the LLM."""
    store = store or get_store()
    ctx.text = clean_input(ctx.text)
    lang = resolve_lang(ctx.text, ctx.lang_pref)
    q = ctx.text

    if wellness.is_crisis(q):
        return _crisis_reply(lang)

    if ctx.mode == "study":
        if not ctx.student:
            return Reply("Please open the Student Zone and enter your access code to use the study helper.", intent="study", lang=lang,
                         actions=[_open("student")])
        system = _study_prompt(lang)
        return Plan(ctx, lang, system, _history_messages(ctx.sid, "study") + [{"role": "user", "content": q}],
                    system, None, study=True)

    ql = q.lower()
    if ql == "date":
        return Reply(f"Today's date is {datetime.now().strftime('%Y-%m-%d')}", intent="clock", lang=lang)
    if ql == "time":
        return Reply(f"The current time is {datetime.now().strftime('%H:%M:%S')}", intent="clock", lang=lang)

    m = re.search(r"(https?://[^\s]+)", q)
    if m:
        return Reply(f"Opening the link: {m.group(0)}...", intent="nav", url=m.group(0), lang=lang)
    words = ql.split()
    if words and words[0] == "open":
        hit = site_links.match_page(" ".join(words[1:]))
        if hit:
            return Reply(f"{hit[0]}...", intent="nav", url=hit[1], lang=lang)
        return Reply("I couldn't find a matching page. Try again with clearer words.", intent="nav", lang=lang, translate=True)

    reply = handle_tools(ctx, lang)
    if reply:
        return reply

    if _OFF_TOPIC_HIT(q):
        return Reply(OFF_TOPIC_REPLY, intent="offtopic", lang=lang, translate=True)

    reply = handle_fee_query(q) or handle_misc(q)
    if reply:
        return reply

    learned = _learned_match(q, store)
    if learned:
        return Reply(learned["answer"], intent="learned", engine="staff", lang=lang)

    cache_key = None
    if sessions.turn_count(ctx.sid) == 0 and ctx.channel == "web":
        cache_key = f"{lang}:{store.version()}:{normalize(q)}"
        hit = sessions.cache_get(cache_key)
        if hit:
            return Reply(**{**hit, "engine": "cache", "reply_id": ""})

    system = _system_prompt(ctx, lang, store)
    qwen_system = (IDENTITY.split("FORMAT:")[0] + (LANG_RULE.format(name=lang_name(lang)) if lang != "en" else "")
                   + "\nFACTS:\n" + knowledge.qwen_context(q, store) + QWEN_TAIL)
    messages = _history_messages(ctx.sid, "chat") + [{"role": "user", "content": q}]
    return Plan(ctx, lang, system, messages, qwen_system, cache_key)


def _OFF_TOPIC_HIT(text):
    return bool(_OFF_TOPIC.search(text))


def _study_prompt(lang):
    from .features import study
    extra = f"\nReply in {lang_name(lang)}." if lang != "en" else ""
    return study.SYSTEM_TUTOR + extra


def finish(plan, text, engine, store=None):
    """Turn raw model text into a Reply: strip markers, fee-check, attach chips and links."""
    store = store or get_store()
    ctx, lang = plan.ctx, plan.lang
    cleaned, unknown, crisis, opens = _extract_markers(text)

    if crisis and not plan.study:
        return _crisis_reply(lang)

    cleaned = strip_internal_labels(cleaned)
    if engine == "qwen":
        cleaned = enforce_length(cleaned)

    if not plan.study and not knowledge.fee_numbers_consistent(cleaned, store):
        fallback = handle_fee_query(ctx.text)
        if fallback:
            return localize(fallback, lang)
        return Reply("I don't have a confirmed figure for that. Please contact the admissions office directly.",
                     intent="fee_guard", engine=engine, lang=lang, unknown=True, chips=CHIPS["unknown"], cards=[contact_card()])

    if not cleaned:
        unknown = True
        cleaned = "I'm sorry, I couldn't put an answer together. The admissions office can help directly."

    reply = Reply(cleaned, intent="study" if plan.study else "llm", engine=engine, lang=lang, unknown=unknown)
    if plan.study:
        return reply
    reply.actions = [_open(p) for p in dict.fromkeys(opens)]
    if unknown:
        reply.chips = CHIPS["unknown"]
        reply.cards = [contact_card()]
    else:
        reply.chips = CHIPS["default"] if not opens else []
        reply.links = site_links.suggest_links(ctx.text + " " + cleaned)
    if plan.cache_key and not unknown and not opens and engine == "gemini":
        sessions.cache_set(plan.cache_key, {k: v for k, v in reply.to_dict().items() if k in (
            "answer", "intent", "lang", "cards", "chips", "actions", "links", "private")} | {"engine": "gemini"})
    return reply


_UNAVAILABLE = ("I'm having trouble reaching my knowledge system right now. Please call the college office on "
                "+91 080 4012 9292 (Mon-Fri 8:30-4:30) or try again in a moment.")


def unavailable_reply(lang="en"):
    return Reply(_UNAVAILABLE, intent="error", engine="none", lang=lang, unknown=True, chips=CHIPS["unknown"], cards=[contact_card()])


# ------------------------------------------------------------------------------------------------
# Public entry points
# ------------------------------------------------------------------------------------------------
def _remember(ctx, reply, store):
    reply.reply_id = reply.reply_id or uuid.uuid4().hex[:12]
    try:
        page = ctx.url.split("?")[0].split("#")[0] if not reply.private else ""
        store.log_message(ctx.sid, "user", ctx.text, lang=reply.lang, page=page, intent=reply.intent, private=reply.private)
        store.log_message(ctx.sid, "bot", reply.answer, reply_id=reply.reply_id, page=page, lang=reply.lang, engine=reply.engine,
                          intent=reply.intent, question=ctx.text, private=reply.private)
        if reply.unknown and not reply.private and reply.intent != "error":
            store.record_unanswered(ctx.text, reason=reply.intent)
        elif reply.intent == "error":
            store.record_unanswered(ctx.text, reason="model_unavailable")
    except StoreError as exc:
        log.warning("could not log exchange: %s", exc)
    if not reply.private:
        mode = "study" if reply.intent == "study" else "chat"
        sessions.save_turn(ctx.sid, ctx.text, reply.answer, mode)
        if legacy_sink:
            try:
                legacy_sink(ctx.sid, "user", ctx.text, None, ctx.url, ctx.user_agent)
                legacy_sink(ctx.sid, "bot", reply.answer, reply.reply_id, ctx.url, ctx.user_agent)
            except Exception:  # noqa: BLE001
                log.exception("legacy sink failed")
    return reply


def respond(ctx, store=None):
    store = store or get_store()
    t0 = time.monotonic()
    plan = prepare(ctx, store)
    if isinstance(plan, Reply):
        reply = localize(plan, plan.lang if plan.lang != "en" else resolve_lang(ctx.text, ctx.lang_pref))
    else:
        try:
            result = llm.generate(plan.system, plan.messages, max_tokens=config.GEMINI_MAX_TOKENS,
                                  temperature=0.25 if not plan.study else 0.5, allow_qwen=False)
        except llm.LLMError:
            result = None
        if result is None and llm.qwen_available():
            try:
                result = llm.generate(plan.qwen_system, plan.messages[-3:], max_tokens=config.LLAMA_MAX_TOKENS, temperature=0.2)
            except llm.LLMError:
                result = None
        reply = finish(plan, result.text, result.engine, store) if result else unavailable_reply(plan.lang)
    _remember(ctx, reply, store)
    log.info("replied intent=%s engine=%s in %.2fs", reply.intent, reply.engine, time.monotonic() - t0)
    return reply


class _Holdback:
    """Releases streamed text but holds back anything that might be a [[MARKER]] so it never flashes on screen."""

    def __init__(self):
        self.raw = ""
        self.sent = 0

    def feed(self, delta):
        self.raw += delta
        text = self.raw
        lead = re.match(r"\s*(\[\[[^\]]*\]\]\s*)+", text)
        start = lead.end() if lead else 0
        if not lead and text.lstrip().startswith("[") and "]]" not in text and len(text) < 32:
            return ""
        body = text[start:]
        cut = body.find("[[")
        safe = body if cut == -1 else body[:cut]
        if cut == -1 and body.endswith("["):
            safe = body[:-1]
        out = safe[self.sent:]
        self.sent = len(safe)
        return out


def respond_stream(ctx, store=None):
    """Yield {"type": "delta"|"reset"|"final", ...} dicts for the SSE endpoint."""
    store = store or get_store()
    plan = prepare(ctx, store)
    if isinstance(plan, Reply):
        reply = localize(plan, plan.lang if plan.lang != "en" else resolve_lang(ctx.text, ctx.lang_pref))
        _remember(ctx, reply, store)
        yield {"type": "final", "reply": reply.to_dict()}
        return

    hold, engine, done = _Holdback(), None, False
    try:
        for kind, payload in llm.generate_stream(plan.system, plan.messages, max_tokens=config.GEMINI_MAX_TOKENS,
                                                 temperature=0.25 if not plan.study else 0.5,
                                                 qwen_system=plan.qwen_system, qwen_messages=plan.messages[-3:]):
            if kind == "delta":
                piece = hold.feed(payload)
                if piece:
                    yield {"type": "delta", "text": piece}
            elif kind == "reset":
                hold = _Holdback()
                yield {"type": "reset"}
            elif kind == "done":
                engine, done = payload["engine"], True
    except llm.LLMError:
        done = False
    reply = finish(plan, hold.raw, engine or "gemini", store) if done and hold.raw.strip() else unavailable_reply(plan.lang)
    _remember(ctx, reply, store)
    yield {"type": "final", "reply": reply.to_dict()}


def page_context(url, store=None):
    """Greeting and chips tailored to the page the visitor is on (feature 4)."""
    u = (url or "").lower()
    if "ibdp" in u or "managebac" in u:
        return {"topic": "ibdp", "greeting": "Looking at the IB Diploma? I can explain the programme, the admission steps and the fees.",
                "chips": [_chip("IBDP admission process", send="What is the IBDP admission process?"), _chip("IBDP fees", send="What is the IBDP fee?"),
                          _chip("PU or IBDP?", open_="compare"), _chip("Talk to the IBDP office", open_="callback")]}
    if re.search(r"contact|campus|infrastructure|visit", u):
        return {"topic": "visit", "greeting": "Want to see the campus? You can book a visit slot or ask me how to get here.",
                "chips": [_chip("Book a campus visit", open_="visit"), _chip("How do I reach the college?", send="How do I contact the college?"),
                          _chip("Request a callback", open_="callback")]}
    if re.search(r"fee|faqs?-pu|pre-university|admission-enquiry-pu|enquiry-pu|academics\.php|\bpu\b", u):
        return {"topic": "pu", "greeting": "Planning for 1st PUC? Ask me about streams, fees, cutoffs and documents.",
                "chips": [_chip("Fees by stream", send="What are the PU fees?"), _chip("Which stream suits me?", open_="advisor"),
                          _chip("Documents needed", open_="documents"), _chip("Book a campus visit", open_="visit")]}
    if re.search(r"student-life|event|achievers|blog", u):
        return {"topic": "life", "greeting": "Curious about life at CJC? Ask about clubs, fests and events.",
                "chips": [_chip("Upcoming events", open_="events"), _chip("Student clubs", send="What clubs does the college have?"),
                          _chip("CJC MUN", send="Tell me about CJC MUN")]}
    return {"topic": "home", "greeting": "Hi, I'm Noah. Ask me anything about Christ Junior College.",
            "chips": CHIPS["default"] + [_chip("Upcoming events", open_="events")]}
