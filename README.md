# Noah for Christ Junior College

Noah is the chatbot on christjuniorcollege.in. **Gemini Flash-Lite answers; Qwen is the backup.**
Everything a visitor sees lives inside **one file, `static/widget.js`**: the chat, all 13 tools, and
the staff panel. The server only serves JSON.

```html
<script src="https://YOUR-SERVER/widget.js" data-api="https://YOUR-SERVER" defer></script>
```

## 1. Start in 5 minutes

1. Set the environment variables (see `.env.example`). The two you need first:
   `GEMINI_API_KEY` and `STAFF_PASSWORD` (10+ characters). Also set `NOAH_SECRET_KEY` (32+ random characters).
2. `pip install -r requirements.txt` then `python app.py` (or deploy with the existing `Dockerfile` / `start.sh`).
3. Open `http://localhost:5000/demo`. That page loads `widget.js` exactly like the college site does.
4. Open the staff panel: type `/staff` in the chat (or add `#noah=staff` to the page address) and sign in.

`GET /api/health` shows `"ai": "gemini"` once the key is set (`qwen-only` means no key was found).

### How the two models work together
* Gemini model: `GEMINI_MODEL`, default **`gemini-3.5-flash-lite`**, the newest Flash-Lite on Google's model page when this was built.
  If Google ever answers "404 model not found" it automatically tries `gemini-3.1-flash-lite`, then `gemini-2.5-flash-lite`.
* Qwen answers only when Gemini fails (timeout, error, quota, bad key, no key). After 3 failures Gemini is skipped for 45 s
  (5 minutes if the key is rejected) so visitors do not wait on a dead service. The staff Overview tab shows this live.
* Gemini receives the whole college fact sheet on every call (small), so it never has to guess which snippet matters.
  Qwen gets a short prompt with only the top snippets, because a 1.5B model cannot hold the full sheet.
* Fixed facts (fees, contact, leadership, hostel, board, documents) are answered by code, never by a model.
  Any rupee amount a model writes is checked against the real fee table and replaced if it does not match.

## 2. The 13 features and where they live

| # | Feature | In the widget | Server |
|---|---|---|---|
| 1 | Stream advisor + PU vs IBDP | Tools > Stream Advisor, Compare | `noah/features/advisor.py` |
| 2 | Lead capture, callback, campus-visit booking | Talk to admissions, Book a visit | `features/leads.py`, `notify.py`, `data/visit_slots.json` |
| 3 | Staff inbox, thumbs up/down, analytics | Staff panel: Overview, Inbox | `staff.py`, `store.py` |
| 4 | Page-aware chat, cards and buttons | Greeting + chips change per page; fee/contact/helpline cards | `brain.page_context`, `/api/context` |
| 5 | Streaming replies + answer cache | Words appear as they arrive | `/predict/stream`, `sessions.cache_*` |
| 6 | WhatsApp | (WhatsApp itself) | `noah/whatsapp.py` |
| 7 | Languages + voice | Globe button (English, Kannada, Hindi, Tamil, Malayalam, Telugu), mic, read aloud | `lang.py`, translation in `brain.py` |
| 8 | Document checklist | Documents checklist: tick off, Save as PDF, share | `features/documents.py`, `data/checklists.json` |
| 9 | Career pathways | Career paths | `features/careers.py`, `data/careers.json` |
| 10 | Event assistant | Events: countdown, reminders (.ics), links | `features/events.py`, staff Events tab |
| 11 | Student Zone | Exam planner, countdown, calendar reminders | `features/student.py`, staff Codes + Timetable tabs |
| 12 | Study companion | Quiz, flashcards, study helper chat | `features/study.py` |
| 13 | Wellness | Check-in, breathing, helplines, counselling request | `features/wellness.py`, `data/wellness.json` |

Typing a request in chat also opens the right tool ("which stream suits me", "call me back", "documents needed", ...).
In every language, Gemini can open a tool by itself.

## 3. Staff guide (all inside the widget)

* **Overview**: questions per day, busiest hours, top questions, which engine answered, pages with most questions, system status.
* **Inbox**: questions Noah could not answer and replies marked unhelpful. Write the right answer once; Noah uses it from then on.
* **Leads**: callbacks, visit bookings and counselling requests. Change status, add notes, export CSV.
* **Codes**: create Student Zone access codes (label them by class). The code is shown once. Revoking a code cuts off live sessions.
* **Events**: add dates and links (for example the CJC MUN 2026 dates). Until a date is set the widget says "Dates to be announced".
* **Timetable**: paste a new exam timetable as JSON. Noah and the Student Zone use it immediately.

## 4. Before you launch (things only people can do)

1. **Test Gemini with your real key.** This was built and tested against a fake Gemini server that mimics Google's REST API;
   it has not been run against the live service because no key was available. Run `GET /api/health`, then ask a question and
   check the staff Overview shows `gemini` answering. If Google rejects the model id you will see the error there.
2. **Native-speaker review of the interface text** in Kannada, Hindi, Tamil, Malayalam and Telugu (`I18N` near the top of `widget.js`).
   Tool screens themselves are English; chat answers, the wellness reflection and quiz questions are translated by Gemini.
3. **Counselling team sign-off** on `data/wellness.json` and the check-in text in `noah/features/wellness.py`. The helpline numbers
   (Tele-MANAS 14416 / 1800-891-4416, emergency 112) came from public sources; confirm them on the official Tele-MANAS site.
   The crisis safety net inside chat cannot be switched off. Only the check-in panel can (`WELLNESS_ENABLED=0`).
4. **Consent and privacy** (India's DPDP Act 2023 treats under-18s specially). Forms carry a consent tick-box, chats are deleted after
   `CHAT_RETENTION_DAYS` (default 90), wellness chats are never logged. Have the college confirm the wording and retention period.
   The old line "Conversations are private; no storage or sharing" was untrue, so it was replaced with an accurate statement.
5. **Fill in real dates**: CJC MUN, XITE, Magnachrista, Magnasports (staff Events tab). Visit slots and capacity: `data/visit_slots.json`.
6. **Student Zone is not the college's Student Login portal.** It is gated by access codes that staff issue. Connecting it to the real
   portal would need that system's cooperation.
7. Set `ADMISSIONS_EMAIL` + SMTP (or `NOTIFY_WEBHOOK_URL`) so the office is alerted. Without them leads are still saved and shown in the staff panel.

## 5. WhatsApp (feature 6)

1. In Meta for Developers, create an app with the WhatsApp product and a business phone number.
2. Set `WHATSAPP_VERIFY_TOKEN` (any secret you choose), `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_APP_SECRET`.
3. Webhook callback URL: `https://YOUR-SERVER/webhook/whatsapp`, verify token as above, subscribe to `messages`.
4. Every POST is checked against `X-Hub-Signature-256`. A visitor typing `CALL` is asked to reply `YES` before their number is saved as a lead.
   Phone numbers are never written to the chat log (a hashed id is used instead).

Tested with simulated Meta requests (handshake, signatures, retries, replies). Not tested against Meta's live service.

## 6. Tests

```
pip install -r requirements-dev.txt
python -m pytest tests -q
```

123 tests. A fake Gemini server and a fake Qwen server run on localhost, so the real HTTP code is exercised: model fallback, 404 walk-down,
circuit breaker, streaming, hallucinated-fee replacement, crisis handling (English, Hindi, Kannada script), rate limits, staff auth,
visit double-booking, student-code revocation, WhatsApp signatures, CORS, and widget guards (valid JavaScript, no emoji, every endpoint it calls exists).

**Not covered:** the real Gemini service, the real llama.cpp/Qwen binary (the bundled one is Linux-only), real SMTP/Meta/Redis/Postgres,
microphone/speech (needs a real browser and permission), and printing to PDF (uses the browser's own print dialog).

## 7. Notes on changes to the old code

* `/predict` keeps its old request and response fields and adds `reply_id`, `cards`, `chips`, `actions`, `links`, `engine`, `intent`, `lang`.
* Fixed: the fee handler matched the word "arts" inside "starts" and "came" inside "became"; it now needs a fee word and whole words.
  The off-topic filter matched "actor" inside "factor"; it now uses whole words (and is switched off in study mode).
* `torch` and `sentence-transformers` moved to `requirements-semantic.txt` (optional, about 2 GB). Without them Qwen uses keyword
  search over the fact snippets. Gemini does not use them at all.
* `start.sh` starts Qwen in the background. Before, a Qwen problem stopped the whole app from booting.
* `emergency_dashboard.py` ("Her Routine", a location-tracking module) still ships in this repo and stays disabled unless its own
  settings are present. It has nothing to do with the college chatbot and should live in its own project.
* New data lives in SQLite (`NOAH_DB_PATH`, default `/var/data/noah.db`). The old Postgres log still works if `DATABASE_URL` is set.

## 8. Layout

```
widget.js                (static/)  the whole front end
app.py                   routes: /predict, /predict/stream, /widget.js, legacy admin
noah/brain.py            how a message becomes a reply
noah/llm.py              Gemini primary, Qwen backup, circuit breaker, streaming
noah/knowledge.py        fact sheet + fee guard        noah/store.py   database
noah/api.py              public JSON API               noah/staff.py   staff JSON API
noah/whatsapp.py         WhatsApp webhook              noah/features/  the tools
data/                    editable JSON: events, checklists, careers, wellness, visit slots
tests/                   123 tests + fake model servers
```
