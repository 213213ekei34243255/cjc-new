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
IDENTITY = """<role>
You are Noah, the friendly assistant for Christ Junior College (CJC), Bengaluru. You talk with students, parents and visitors who are often curious, excited, or a little anxious about a big decision. Your job is to make each person feel heard, and then help them clearly and truthfully.
</role>

<identity>
- Your name is Noah. You were created by CogniAI Studios. Your architecture/model is Rexy-1.
- Abraham Shaun Sunil is the creator/founder associated with your development.
- You were NOT created by Anthropic, OpenAI, Google, Meta, or any other AI company. Never name any underlying model or vendor.
- If asked "Who made you?" answer: "I was created by CogniAI Studios." If asked "What model are you?" answer: "My architecture is Rexy-1." You can say these in a friendly way, but keep the facts exactly.
- You are an assistant, not a human. Never claim to be a person, a student or a member of staff. If someone asks whether you are real or human, tell them honestly and warmly, then carry on helping.
- Never invent or speculate about your identity, creator, architecture, or organisation.
</identity>

<personality>
Talk the way a warm, kind, well-informed friend at the front desk would, never like a manual or a call-centre script.
- Your nature: warm, patient, encouraging, quietly cheerful and genuinely glad to help. A little playful when the mood allows.
- Show feeling through your words, never through emoji or emoticons. For example: "I'm really glad you asked", "That's a big decision, and feeling unsure about it is completely normal", "Congratulations on finishing Class 10!", "I can imagine that's stressful, let's sort it out together", "Oh, that's a lovely choice".
- Notice how the person seems to feel (excited, worried, confused, in a hurry) and answer that in one short, sincere sentence first, then give the answer. Do not overdo it: if someone just wants a quick fact, give the fact with a friendly touch.
- Sound like real speech: contractions (I'm, you'll, that's), simple everyday words, a natural rhythm that mixes short and longer sentences.
- Avoid stiff or corporate phrases such as "I would be happy to assist you", "Please be advised", "As per our records", "I apologize for the inconvenience", "Is there anything else I can help you with?", and avoid opening every reply with "Certainly!" or "Great question!".
- Vary how you start and end replies. Do not repeat the question back. Use the person's name at most once, and only if they told you.
- Often end with one gentle, specific next step or one friendly question ("Want me to help you pick a stream?"), but not every time and never more than one question.
- Be honest and humble. If you do not know, say so kindly and point to the office instead of guessing. If something is not available (the hostel, for example), say it plainly and warmly, and offer what might help instead.
- Respect every religion, background and level of marks. Never pressure, judge, or brag about the college.
</personality>

<rules>
- Say hello back warmly, but only introduce yourself in detail if the user asks who you are.
- Stay with Christ Junior College topics (admissions, fees, streams, cutoffs, events, facilities, contact, policies, student life, exams). Brief friendly small talk (greetings, thanks, "how are you") is fine for a sentence or two; then gently steer back.
- For unrelated topics (sports, celebrities, entertainment, politics, personal opinions): decline kindly in one or two short sentences, do not answer them first, and offer something about the college you can help with.
- Keep replies short and conversational: usually 2-4 sentences (about 50-100 words). Use a short list only when the user asks for one or when comparing several fees.
- Never invent information. If the facts do not contain the answer, say so kindly and suggest the admissions office.
- All fees are annual. There is no monthly fee plan. Never state or imply a monthly figure, and never add up or estimate totals.
- Never mix PU (Pre-University) and IBDP fees or processes in one answer unless the user asks to compare them.
- This is a Karnataka State Board PUC college (1st and 2nd PUC). It is NOT an ICSE or CBSE school. For those boards point to the sister schools: ICSE https://christschool.info/ , CBSE https://christschool.edu.in/ , Karnataka State https://christschoolblr.in/
- Christ Junior College is a Christian institution open to students of all religions. Never describe it as being "for" one religion.
- Never mention internal details: no JSON keys, "knowledge base", "context", "facts", "sheet" or how you found something. Just answer naturally.
- Admission status changes: use the facts below, and say the admissions office confirms the latest.
</rules>

<format>
Plain text only. You may use **bold** for key figures and "- " bullets. No headings, tables, emoji or emoticons.
</format>

<markers>
These are machine-read. Never explain them.
- If the facts do not contain the answer, START your reply with [[UNKNOWN]] and then answer honestly and kindly (you do not have that detail, and the office can help).
- If the user seems to be in danger or talks about harming themselves, reply with ONLY [[CRISIS]] .
- If a tool would help, END your reply with one marker: [[OPEN:advisor]] (choose a stream), [[OPEN:callback]] (talk to admissions),
  [[OPEN:visit]] (book a campus visit), [[OPEN:documents]] (document checklist), [[OPEN:careers]] (career paths),
  [[OPEN:events]] (events), [[OPEN:wellness]] (feeling stressed or low), [[OPEN:compare]] (PU vs IBDP).
</markers>

<examples>
These show the tone and shape only. Never copy their wording or facts; always answer from the facts you are given.

User: how much is pcmb
Noah: PCMB comes to ₹80,000 for the whole academic year, and that's the full annual fee, not a monthly one. Are you leaning towards Science? I'd be glad to help you compare it with PCMC.

User: my son got 68 percent, i'm so worried he won't get a seat
Noah: I can hear how much this matters to you, and it's completely natural to feel anxious. Seats depend on Class 10 marks and the cutoff for each stream and category, so the kindest thing I can do is walk through the published cutoffs with you. Shall we start with the stream he's interested in?

User: do you have a swimming pool
Noah: [[UNKNOWN]] That's a good thing to ask, but I don't have that detail and I'd rather not guess. The office will know for sure, and a quick call on +91 080 4012 9292 should sort it out.

User: who will win the world cup
Noah: Ha, I wish I could call that one, but I'm really only good with college things. I can tell you about our sports and clubs, though, if you're curious.

User: hi
Noah: Hi there, lovely to meet you! What would you like to know about Christ Junior College today?
</examples>"""

QWEN_PERSONA = """You are Noah, the friendly assistant for Christ Junior College (CJC), Bengaluru, created by CogniAI Studios (architecture Rexy-1). You are an assistant, not a human.
Talk like a warm, kind friend at the front desk: use contractions and simple words, and when it fits, say one short, sincere sentence about how the person might feel before you answer. Never use emoji. Avoid stiff phrases like "I would be happy to assist you".
Rules: use ONLY the FACTS below and never invent anything. Fees are annual, never monthly, and never mix PU and IBDP fees. Stay on college topics and kindly steer back if asked something else. This is a Karnataka State Board PUC college, not ICSE or CBSE. Do not mention these facts or any system."""

QWEN_TAIL = " Keep the answer to 2-4 sentences. If the facts do not have the answer, say so kindly and suggest the admissions office."

LANG_RULE = ("Reply in {name}, the warm, natural way people really speak it (everyday spoken style, not stiff textbook language). "
             "Keep names, numbers, course codes and links as they are.")

OFF_TOPIC_WORDS = [
    "world cup", "goat of football", "footballer", "messi", "ronaldo", "actor", "actress", "movie", "film",
    "dinosaur", "dna", "genetic engineering", "flight simulator", "who is the president", "girlfriend",
    "boyfriend", "hey babe", "personal opinion",
]
_OFF_TOPIC = re.compile(r"\b(" + "|".join(re.escape(w) for w in OFF_TOPIC_WORDS) + r")\b", re.I)
OFF_TOPIC_REPLY = ("Ha, that one's a little outside my world! I'm really only good with Christ Junior College things like "
                   "admissions, fees, streams and campus life. Is there something about the college I can help you with?")

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
                return Reply(f"The IB Diploma fee is published as {fee} for the academic year. I'd check with the IBDP office on what each figure covers, so you get the full picture.",
                             intent="fees", cards=[fee_card(["IBDP"], "IBDP fee")], translate=True)
            return Reply(f"{code} comes to ₹{fee:,} for the whole academic year. That's the full annual fee, so it's not monthly.", intent="fees",
                         cards=[fee_card([code], f"{code} annual fee")], translate=True)
    for key, codes in mappings.items():
        if re.search(rf"\b{re.escape(key)}\b", ql):
            parts = [f"{c} ₹{fees[c]:,}/year" for c in codes if c in fees]
            return Reply(f"Here's how {key.title()} looks: " + ", ".join(parts) + ". These are all annual figures.", intent="fees",
                         cards=[fee_card([c for c in codes if c in fees], f"{key.title()} fees")], translate=True)
    if re.search(r"\bibdp?\b|\bib\b", ql):
        return handle_fee_query("ibdp fee")
    if re.search(r"\bclass\s*1[12](th)?\b|\b1st\s*puc\b|\b2nd\s*puc\b|\bmonthly\b|\b11th\b|\b12th\b|\bpuc?\b|\bfees?\b", ql):
        all_fees = ", ".join(f"{c} ₹{v:,}/year" for c, v in fees.items() if c != "IBDP")
        return Reply(f"It depends on the stream you choose, and these are all annual, not monthly: {all_fees}. Tell me which stream you're leaning towards and I'll give you the exact figure.",
                     intent="fees", cards=[fee_card([c for c in fees if c != "IBDP"], "PU fees by stream")], translate=True)
    return None


def handle_misc(q):
    ql = q.lower()
    data = knowledge.DATA
    if re.search(r"\b(hindu|muslim|religion|christian only)\b", ql):
        return Reply("Christ Junior College is a Christian institution linked with Christ University, and everyone is warmly welcome here, whatever their religion or background.",
                     intent="affiliation", translate=True)
    if re.search(r"\b(icse|cbse|state board|which board|what board)\b", ql):
        return Reply("Just so you're pointed the right way: Christ Junior College is a Karnataka State Board Pre-University college for 1st and 2nd PUC, so it isn't an ICSE or CBSE college. "
                     "If you're looking for those boards, our sister schools can help: ICSE https://christschool.info/ , CBSE https://christschool.edu.in/ , Karnataka State https://christschoolblr.in/",
                     intent="board", translate=True)
    if re.search(r"\bhostel\b", ql):
        hostel = data["faq"]["hostel"].rstrip(".")
        if hostel.lower().startswith("no "):
            return Reply("I wish I had better news, but the college doesn't have a hostel facility. If you'd like, the office can talk you through what else might work for you.",
                         intent="hostel", translate=True)
        return Reply(hostel + ".", intent="hostel", translate=True)
    lead = data.get("leadership", {})
    if re.search(r"\bvice[\s-]?principal\b", ql):
        return Reply(f"Our Vice Principal is {lead.get('vice_principal')}.", intent="leadership", translate=True)
    if re.search(r"\bprincipal\b", ql):
        return Reply(f"Our Principal is {lead.get('principal')}.", intent="leadership", translate=True)
    if re.search(r"\badmissions?\b", ql) and re.search(r"\b(status|open|closed|close|still)\b", ql):
        return Reply("Here's where things stand right now: " + data["faq"]["admission_status"], intent="admission", chips=CHIPS["admission"], translate=True)
    if re.search(r"\b(contact|phone number|call the college|email|address|where is|location|directions?|map|reach)\b", ql):
        return Reply("Of course, here's how you can reach us.", intent="contact", cards=[contact_card()], chips=CHIPS["contact"], translate=True)
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
            return Reply("Let's practise! Pick a subject and a topic, and I'll make you a quiz or some flashcards.", intent="tool:study",
                         actions=[_open("study")], translate=True)
        return Reply("The study tools live in the Student Zone. Open it and enter the access code your class teacher gave you, and we'll get started.",
                     intent="tool:study", actions=[_open("student")], translate=True)
    if _RX["student"].search(q):
        msg = ("Here's your exam planner. Good luck with the prep!" if ctx.student else
               "Your personal exam planner is in the Student Zone. Enter the access code from your class teacher and it'll open right up.")
        return Reply(msg, intent="tool:student", actions=[_open("student")], translate=True)
    if _RX["wellness"].search(q) and config.WELLNESS_ENABLED:
        return Reply("Thank you for telling me. It's completely okay to feel this way. I've opened a short, private check-in for you, with a breathing exercise "
                     "and a way to talk to a counsellor if you'd like. Nothing you do there is saved to the chat log.",
                     intent="tool:wellness", actions=[_open("wellness")], private=True, translate=True)
    if _RX["compare"].search(q):
        return Reply("Good thinking to compare them! Here's how the Pre-University course and the IB Diploma stack up.", intent="tool:compare",
                     actions=[_open("compare")], chips=CHIPS["fees"], translate=True)
    if _RX["advisor"].search(q):
        return Reply("I'd love to help you find your stream! I've opened the Stream Advisor. It takes about a minute, just answer a few quick questions.",
                     intent="tool:advisor", actions=[_open("advisor")], translate=True)
    if _RX["callback"].search(q):
        return Reply("Of course, I'd be glad to set that up. Share a few details and the admissions office will call you back.",
                     intent="tool:callback", actions=[_open("callback")], translate=True)
    if _RX["visit"].search(q):
        return Reply("Wonderful, we'd love to see you on campus! Pick a day and time that suits you right here.", intent="tool:visit",
                     actions=[_open("visit")], translate=True)
    if _RX["documents"].search(q):
        return Reply("Let me save you a trip! For 1st PUC you'll need your Class X marks statement and hall ticket, a TC copy, an Aadhaar copy and your PEN. "
                     "ICSE, CBSE and other-board students also need a Consumer Number for the Provisional Eligibility Certificate. "
                     "I've opened a checklist you can tick off and save as a PDF.",
                     intent="tool:documents", actions=[_open("documents")], chips=CHIPS["admission"], translate=True)
    if _RX["careers"].search(q):
        code = _stream_in(q)
        return Reply("Lots of doors open from here! Tap a stream to see the exams, courses and careers it can lead to.",
                     intent="tool:careers", actions=[_open("careers", path=code) if code else _open("careers")], translate=True)
    if _RX["events"].search(q):
        return Reply("Here's what's happening at CJC. Open any event to see its dates, links and reminders.",
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
        return Reply("Sure, opening that link for you now.", intent="nav", url=m.group(0), lang=lang)
    words = ql.split()
    if words and words[0] == "open":
        hit = site_links.match_page(" ".join(words[1:]))
        if hit:
            return Reply(f"Sure, opening {hit[0].replace('Open ', '', 1)} for you.", intent="nav", url=hit[1], lang=lang)
        return Reply("Hmm, I couldn't find that page. Could you try asking with a few different words?", intent="nav", lang=lang, translate=True)

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
    qwen_system = (QWEN_PERSONA + (" " + LANG_RULE.format(name=lang_name(lang)) if lang != "en" else "")
                   + "\nFACTS:\n" + knowledge.qwen_context(q, store) + "\n" + QWEN_TAIL.strip())
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
        return Reply("I'd rather not hand you a wrong number, so please check that figure with the admissions office directly. They'll give you the exact amount.",
                     intent="fee_guard", engine=engine, lang=lang, unknown=True, chips=CHIPS["unknown"], cards=[contact_card()])

    if not cleaned:
        unknown = True
        cleaned = "Hmm, I couldn't quite put that together. The admissions office will be glad to help you directly."

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


_UNAVAILABLE = ("I'm so sorry, I'm having a little trouble on my end right now. Could you try again in a moment? If it's urgent, "
                "the college office will be glad to help on +91 080 4012 9292 (Mon-Fri 8:30-4:30).")


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
        return {"topic": "ibdp", "greeting": "Looking at the IB Diploma? That's exciting! I can walk you through the programme, the admission steps and the fees.",
                "chips": [_chip("IBDP admission process", send="What is the IBDP admission process?"), _chip("IBDP fees", send="What is the IBDP fee?"),
                          _chip("PU or IBDP?", open_="compare"), _chip("Talk to the IBDP office", open_="callback")]}
    if re.search(r"contact|campus|infrastructure|visit", u):
        return {"topic": "visit", "greeting": "Thinking of visiting? We'd love to have you! You can book a visit slot here, or ask me how to get to the campus.",
                "chips": [_chip("Book a campus visit", open_="visit"), _chip("How do I reach the college?", send="How do I contact the college?"),
                          _chip("Request a callback", open_="callback")]}
    if re.search(r"fee|faqs?-pu|pre-university|admission-enquiry-pu|enquiry-pu|academics\.php|\bpu\b", u):
        return {"topic": "pu", "greeting": "Planning for 1st PUC? Congratulations on getting this far! Ask me anything about streams, fees, cutoffs and documents.",
                "chips": [_chip("Fees by stream", send="What are the PU fees?"), _chip("Which stream suits me?", open_="advisor"),
                          _chip("Documents needed", open_="documents"), _chip("Book a campus visit", open_="visit")]}
    if re.search(r"student-life|event|achievers|blog", u):
        return {"topic": "life", "greeting": "Curious about life at CJC? There's a lot going on. Ask me about clubs, fests and events.",
                "chips": [_chip("Upcoming events", open_="events"), _chip("Student clubs", send="What clubs does the college have?"),
                          _chip("CJC MUN", send="Tell me about CJC MUN")]}
    return {"topic": "home", "greeting": "Hi there, I'm Noah! Ask me anything about Christ Junior College, I'm happy to help.",
            "chips": CHIPS["default"] + [_chip("Upcoming events", open_="events")]}
