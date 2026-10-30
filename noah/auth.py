"""Signed bearer tokens for staff and students.

The widget runs on another origin (christjuniorcollege.in) than the API, so cookies would be
third-party cookies and get blocked. Tokens travel in the Authorization header instead and live in
sessionStorage, which dies with the tab.
"""

import hashlib
import hmac
import logging
import secrets
import time

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from . import config

log = logging.getLogger("noah.auth")

_secret = config.SECRET_KEY
if not _secret:
    # Tokens issued before a restart stop working. Set NOAH_SECRET_KEY to make them survive restarts.
    _secret = secrets.token_hex(32)
    log.warning("NOAH_SECRET_KEY not set - using a random key; staff/student sessions reset on restart")


def _ser(kind):
    return URLSafeTimedSerializer(_secret, salt=f"noah-{kind}")


def make_token(kind, payload):
    return _ser(kind).dumps(payload)


def read_token(kind, token, max_age_hours):
    if not token:
        return None
    try:
        return _ser(kind).loads(token, max_age=max_age_hours * 3600)
    except (BadSignature, SignatureExpired):
        return None


def bearer(request):
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return ""


def password_matches(given):
    expected = config.STAFF_PASSWORD
    if not expected or not given:
        return False
    return hmac.compare_digest(hashlib.sha256(given.encode()).digest(), hashlib.sha256(expected.encode()).digest())


def staff_configured():
    return len(config.STAFF_PASSWORD) >= 10


def staff_token():
    return make_token("staff", {"role": "staff", "iat": int(time.time())})


def staff_from(request):
    data = read_token("staff", bearer(request), config.STAFF_TOKEN_HOURS)
    return data if isinstance(data, dict) and data.get("role") == "staff" else None


def student_token(code_row):
    return make_token("student", {"cid": code_row["id"], "label": code_row["label"], "course": code_row.get("course", "")})


def student_from(request_or_token, store=None):
    token = request_or_token if isinstance(request_or_token, str) else (
        bearer(request_or_token) or request_or_token.headers.get("X-Student-Token", ""))
    data = read_token("student", token, config.STUDENT_TOKEN_HOURS)
    if not isinstance(data, dict) or "cid" not in data:
        return None
    if store is not None:
        try:
            if not store.student_code_active(data["cid"]):
                return None
        except Exception:  # noqa: BLE001 - if the DB is down, deny rather than guess
            return None
    return data
