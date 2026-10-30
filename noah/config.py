"""All environment-driven settings in one place. Nothing here raises on a missing value:
a missing optional setting turns the feature off instead of taking the app down."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


def env(name, default=""):
    return os.environ.get(name, default).strip()


def env_int(name, default, low=None, high=None):
    try:
        value = int(os.environ.get(name, default))
    except (TypeError, ValueError):
        value = default
    if low is not None:
        value = max(low, value)
    if high is not None:
        value = min(high, value)
    return value


def env_bool(name, default=False):
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


# ---- Gemini (primary) ------------------------------------------------------
GEMINI_API_KEY = env("GEMINI_API_KEY") or env("GOOGLE_API_KEY")
# Latest Flash-Lite at the time of writing is gemini-3.5-flash-lite (stable). If Google
# rejects the id with 404 the client walks down GEMINI_MODEL_FALLBACKS before using Qwen.
GEMINI_MODEL = env("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_MODEL_FALLBACKS = [m.strip() for m in env("GEMINI_MODEL_FALLBACKS", "gemini-3.1-flash-lite,gemini-2.5-flash-lite").split(",") if m.strip()]
GEMINI_API_BASE = env("GEMINI_API_BASE", "https://generativelanguage.googleapis.com").rstrip("/")
GEMINI_TIMEOUT = env_int("GEMINI_TIMEOUT", 25, 3, 120)
GEMINI_MAX_TOKENS = env_int("GEMINI_MAX_TOKENS", 700, 64, 4000)

# ---- Qwen via llama-server (backup) ------------------------------------------
LLAMA_URL = env("LLAMA_URL", "http://127.0.0.1:8080/v1/chat/completions")
LLAMA_TIMEOUT = env_int("LLAMA_TIMEOUT", 90, 5, 300)
LLAMA_MAX_TOKENS = env_int("LLAMA_MAX_TOKENS", 260, 32, 1000)
QWEN_ENABLED = env_bool("QWEN_ENABLED", True)

# ---- Storage / state ---------------------------------------------------------
REDIS_URL = env("REDIS_URL")
DATABASE_URL = env("DATABASE_URL")          # legacy Postgres chat log (optional)
CHAT_RETENTION_DAYS = env_int("CHAT_RETENTION_DAYS", 90, 1, 3650)


def default_db_path():
    explicit = env("NOAH_DB_PATH")
    if explicit:
        return explicit
    persistent = Path("/var/data")
    if persistent.is_dir() and os.access(persistent, os.W_OK):
        return str(persistent / "noah.db")
    return str(ROOT / "noah.db")


# ---- Security ------------------------------------------------------------------
SECRET_KEY = env("NOAH_SECRET_KEY")              # signs staff + student tokens
STAFF_PASSWORD = env("STAFF_PASSWORD") or env("ADMIN_API_KEY")
STAFF_TOKEN_HOURS = env_int("STAFF_TOKEN_HOURS", 8, 1, 72)
STUDENT_TOKEN_HOURS = env_int("STUDENT_TOKEN_HOURS", 12, 1, 168)

ALLOWED_ORIGINS = {
    "https://christjuniorcollege.in",
    "https://www.christjuniorcollege.in",
    "https://byncai.net",
    "https://www.byncai.net",
    "https://www.cogniaistudios.com",
    "https://cogniaistudios.com",
}
ALLOWED_ORIGINS |= {o.strip().rstrip("/") for o in env("EXTRA_ALLOWED_ORIGINS").split(",") if o.strip()}

# ---- Limits --------------------------------------------------------------------
MAX_MESSAGE_CHARS = env_int("MAX_MESSAGE_CHARS", 1200, 100, 8000)
RATE_CHAT_PER_MIN_IP = env_int("RATE_CHAT_PER_MIN_IP", 30, 1, 1000)
RATE_CHAT_PER_MIN_SESSION = env_int("RATE_CHAT_PER_MIN_SESSION", 15, 1, 1000)
RATE_FORMS_PER_HOUR_IP = env_int("RATE_FORMS_PER_HOUR_IP", 10, 1, 1000)
RATE_STUDY_PER_MIN = env_int("RATE_STUDY_PER_MIN", 6, 1, 1000)
TRUST_PROXY_HOPS = env_int("TRUST_PROXY_HOPS", 1, 0, 5)   # 1 on Render

# ---- Notifications (all optional) -----------------------------------------------
SMTP_HOST = env("SMTP_HOST")
SMTP_PORT = env_int("SMTP_PORT", 587, 1, 65535)
SMTP_USER = env("SMTP_USER")
SMTP_PASSWORD = env("SMTP_PASSWORD")
SMTP_FROM = env("SMTP_FROM") or SMTP_USER
ADMISSIONS_EMAIL = env("ADMISSIONS_EMAIL")       # leads + visit bookings go here
COUNSELLING_EMAIL = env("COUNSELLING_EMAIL")     # counselling requests go here
NOTIFY_WEBHOOK_URL = env("NOTIFY_WEBHOOK_URL")   # Slack / Zapier / Sheets style JSON webhook

# ---- WhatsApp Cloud API (optional) -----------------------------------------------
WA_VERIFY_TOKEN = env("WHATSAPP_VERIFY_TOKEN")
WA_ACCESS_TOKEN = env("WHATSAPP_ACCESS_TOKEN")
WA_PHONE_NUMBER_ID = env("WHATSAPP_PHONE_NUMBER_ID")
WA_APP_SECRET = env("WHATSAPP_APP_SECRET")
WA_GRAPH_VERSION = env("WHATSAPP_GRAPH_VERSION", "v21.0")
WA_GRAPH_BASE = env("WHATSAPP_GRAPH_BASE", "https://graph.facebook.com").rstrip("/")

# ---- Feature flags ----------------------------------------------------------------
WELLNESS_ENABLED = env_bool("WELLNESS_ENABLED", True)   # check-in panel; crisis safety net is always on
STUDENT_ZONE_ENABLED = env_bool("STUDENT_ZONE_ENABLED", True)
