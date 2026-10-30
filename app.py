import csv
import io
import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime
from functools import wraps

from flask import Flask, Response, jsonify, make_response, request, send_file, send_from_directory, stream_with_context
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix

from Veronica import load_knowledge_base, save_knowledge_base
from noah import auth, brain, config, llm
from noah.api import api_bp
from noah.features import events as events_feature
from noah.lang import LANGS
from noah.limiter import limiter
from noah.staff import staff_bp
from noah.store import StoreError, get_store
from noah.whatsapp import whatsapp_bp

try:                                    # legacy Postgres chat log + export (optional)
    import psycopg2
    import psycopg2.extras
except ImportError:                     # pragma: no cover
    psycopg2 = None

try:                                    # unrelated "Her Routine" module that shipped in this repo
    from emergency_dashboard import emergency_bp
except Exception:                       # noqa: BLE001 - it must never stop the chatbot booting
    emergency_bp = None

# ---- Configuration ----
logging.basicConfig(level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO))
app = Flask(__name__)
if config.TRUST_PROXY_HOPS:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=config.TRUST_PROXY_HOPS, x_proto=config.TRUST_PROXY_HOPS)
app.register_blueprint(api_bp)
app.register_blueprint(staff_bp)
app.register_blueprint(whatsapp_bp)
if emergency_bp is not None:
    app.register_blueprint(emergency_bp)

ALLOWED_ORIGINS = config.ALLOWED_ORIGINS
CORS(app,
     resources={r"/predict.*": {"origins": list(ALLOWED_ORIGINS)}, r"/api/.*": {"origins": list(ALLOWED_ORIGINS)}},
     methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
     allow_headers=["Content-Type", "Authorization", "X-Student-Token"],
     max_age=86400)

# Legacy knowledge base file (kept for the /save admin endpoint; answers now come from veronica_memory.json + staff-taught answers)
knowledge_base = load_knowledge_base("knowledge_base.json")

DATABASE_URL = config.DATABASE_URL
if not DATABASE_URL:
    app.logger.warning("DATABASE_URL not set: legacy Postgres log/export disabled (Noah's own SQLite store is still active).")

ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY")


def require_admin_key(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not ADMIN_API_KEY:
            app.logger.error("ADMIN_API_KEY not set - refusing admin request for safety.")
            return jsonify({"error": "Admin endpoint not configured"}), 503
        provided = request.headers.get("X-API-Key")
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            provided = provided or auth_header.split(" ", 1)[1]
        if provided != ADMIN_API_KEY:
            return jsonify({"error": "Unauthorized"}), 401
        return fn(*args, **kwargs)
    return wrapper


# ---- legacy Postgres log ----
def get_db_conn():
    if not DATABASE_URL or psycopg2 is None:
        raise RuntimeError("DATABASE_URL / psycopg2 not configured")
    return psycopg2.connect(DATABASE_URL, sslmode=os.environ.get("PGSSLMODE", "prefer"))


def init_db():
    if not DATABASE_URL or psycopg2 is None:
        return
    try:
        with get_db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                CREATE TABLE IF NOT EXISTS veronica_messages (
                    id SERIAL PRIMARY KEY, session_id TEXT, role TEXT, message TEXT, reply_id TEXT,
                    url TEXT, user_agent TEXT, created_at TIMESTAMPTZ DEFAULT now()
                );""")
                conn.commit()
    except Exception:
        app.logger.exception("Failed to initialize legacy DB")


def db_insert_message(session_id, role, message, reply_id=None, url=None, user_agent=None):
    if not DATABASE_URL or psycopg2 is None:
        return
    try:
        with get_db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO veronica_messages (session_id, role, message, reply_id, url, user_agent, created_at)"
                    " VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (session_id, role, message, reply_id, url, user_agent, datetime.utcnow()))
                conn.commit()
    except Exception:
        app.logger.exception("db_insert_message failed")


def fetch_all_conversations():
    if not DATABASE_URL or psycopg2 is None:
        return []
    try:
        with get_db_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("SELECT session_id, role, message, reply_id, url, user_agent, created_at FROM veronica_messages ORDER BY created_at ASC")
                return [dict(r) for r in cur.fetchall()]
    except Exception:
        app.logger.exception("fetch_all_conversations failed")
        return []


init_db()
brain.legacy_sink = db_insert_message if (DATABASE_URL and psycopg2) else None


def _housekeeping():
    """Seed events and delete chat logs older than the retention period; repeats every 6 hours."""
    try:
        store = get_store()
        events_feature.seed(store)
        removed = store.purge_old()
        if removed:
            app.logger.info("retention: removed %s old rows", removed)
    except StoreError:
        app.logger.exception("housekeeping failed")
    timer = threading.Timer(6 * 3600, _housekeeping)
    timer.daemon = True
    timer.start()


_housekeeping()


@app.before_request
def log_request():
    app.logger.debug("Incoming %s %s", request.method, request.path)


# ---- chat ----
def _session_id(data):
    raw = str(data.get("session_id") or data.get("sid") or "")
    ok = 8 <= len(raw) <= 64 and all(ch.isalnum() or ch in "-_" for ch in raw)
    return raw if ok else "anon-" + uuid.uuid4().hex[:16]


def _build_ctx(data):
    text = brain.clean_input(data.get("message", ""))
    lang = data.get("lang") or "en"
    token = request.headers.get("X-Student-Token", "") or auth.bearer(request)
    student = auth.student_from(token, get_store()) if token else None
    return brain.Ctx(
        text=text,
        sid=_session_id(data),
        url=str(data.get("url") or "")[:300],
        lang_pref=lang if lang in LANGS else "en",
        student=student,
        mode="study" if data.get("mode") == "study" else "chat",
        ip=request.remote_addr or "",
        user_agent=str(data.get("user_agent") or request.headers.get("User-Agent", ""))[:300],
    )


def _chat_gate(ctx):
    if not limiter.allow("chat-ip", ctx.ip, config.RATE_CHAT_PER_MIN_IP, 60) or \
            not limiter.allow("chat-sid", ctx.sid, config.RATE_CHAT_PER_MIN_SESSION, 60):
        return jsonify({"answer": "You're sending messages very fast. Please wait a few seconds.", "error": "rate_limited"}), 429
    return None


@app.route("/predict", methods=["POST"], strict_slashes=False)
def predict():
    try:
        data = request.get_json(silent=True) or {}
        ctx = _build_ctx(data)
        if not ctx.text:
            return jsonify({"answer": "Invalid input"}), 400
        blocked = _chat_gate(ctx)
        if blocked:
            return blocked
        return jsonify(brain.respond(ctx).to_dict()), 200
    except Exception:
        app.logger.exception("Error in /predict")
        return jsonify({"error": "An unexpected error occurred."}), 500


@app.route("/predict/stream", methods=["POST"], strict_slashes=False)
def predict_stream():
    """Server-sent events: {"type":"delta","text":..}* then one {"type":"final","reply":{..}}."""
    data = request.get_json(silent=True) or {}
    ctx = _build_ctx(data)
    if not ctx.text:
        return jsonify({"answer": "Invalid input"}), 400
    blocked = _chat_gate(ctx)
    if blocked:
        return blocked

    def events():
        try:
            for event in brain.respond_stream(ctx):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception:
            app.logger.exception("Error in /predict/stream")
            yield f"data: {json.dumps({'type': 'error'})}\n\n"

    return Response(stream_with_context(events()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})


# ---- admin / legacy ----
@app.route("/export_conversations", methods=["GET"])
@require_admin_key
def export_conversations():
    try:
        rows = fetch_all_conversations()
        if not rows:
            return jsonify({"ok": True, "file": None, "message": "No conversation rows found or DB not configured."})
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["session_id", "role", "message", "reply_id", "url", "user_agent", "created_at"])
        for r in rows:
            writer.writerow([r.get("session_id"), r.get("role"), (r.get("message") or "").replace("\n", "\\n"),
                             r.get("reply_id"), r.get("url"), r.get("user_agent"),
                             r.get("created_at").isoformat() if r.get("created_at") else ""])
        output.seek(0)
        return send_file(io.BytesIO(output.getvalue().encode("utf-8")), mimetype="text/csv", as_attachment=True,
                         download_name="veronica_conversations.csv")
    except Exception:
        app.logger.exception("export_conversations failed")
        return jsonify({"ok": False, "message": "Export failed"}), 500


@app.route("/widget.js")
def widget_js():
    resp = send_from_directory(app.static_folder, "widget.js")
    resp.headers["Cache-Control"] = f"public, max-age={config.env_int('WIDGET_CACHE_SECONDS', 0, 0, 86400)}"
    return resp


@app.route("/")
def home():
    return send_from_directory("templates", "index.html")


@app.route("/founders")
def founder():
    return send_from_directory("templates", "founders.html")


@app.route("/cogniai")
def cogniai():
    return send_from_directory("templates", "cogniai.html")


@app.route("/about")
def pro():
    return send_from_directory("templates", "about.html")


@app.route("/services")
def details():
    return send_from_directory("templates", "services.html")


@app.route("/contact")
def contact():
    return send_from_directory("templates", "contact.html")


@app.route("/notification")
def getpro():
    return send_from_directory("templates", "notifications.html")


@app.route("/demo")
def demo():
    """A stand-in college page for trying the widget locally (loads widget.js exactly like the real site does)."""
    return send_from_directory("templates", "demo.html")


@app.route("/submit-details", methods=["POST"])
def submit_details():
    return jsonify({"message": "Form submitted successfully!"})


@app.route("/static/<path:path>")
def static_files(path):
    return send_from_directory("static", path)


@app.route("/save", methods=["POST"])
@require_admin_key
def save():
    global knowledge_base
    new_knowledge_base = (request.get_json(silent=True) or {}).get("knowledge_base")
    if not isinstance(new_knowledge_base, dict):
        return jsonify({"error": "knowledge_base must be a JSON object"}), 400
    save_knowledge_base("knowledge_base.json", new_knowledge_base)
    knowledge_base = new_knowledge_base
    return jsonify({"message": "Knowledge base saved successfully!"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug_mode, threaded=True)
