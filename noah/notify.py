"""Tell the college office about a new lead / visit / counselling request.

Every channel is optional and best-effort: the request is already saved in the database before this
runs, so a broken mail server never loses a parent's enquiry.
"""

import logging
import smtplib
import threading
from email.message import EmailMessage

import requests

from . import config

log = logging.getLogger("noah.notify")


def _send_email(to, subject, body):
    if not (config.SMTP_HOST and to and config.SMTP_FROM):
        return False
    msg = EmailMessage()
    msg["From"] = config.SMTP_FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as smtp:
            smtp.ehlo()
            if config.SMTP_PORT != 25:
                smtp.starttls()
                smtp.ehlo()
            if config.SMTP_USER:
                smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
            smtp.send_message(msg)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("email notification failed: %s", exc)
        return False


def _post_webhook(payload):
    if not config.NOTIFY_WEBHOOK_URL:
        return False
    try:
        # "text" makes it work as a Slack incoming webhook as-is; the rest suits Zapier / Make / Sheets.
        resp = requests.post(config.NOTIFY_WEBHOOK_URL, json={"text": payload["summary"], **payload}, timeout=10)
        return resp.ok
    except requests.RequestException as exc:
        log.warning("webhook notification failed: %s", exc)
        return False


def _summary(kind, lead):
    bits = [f"{k}: {v}" for k, v in lead.items() if v and k not in ("consent",)]
    return f"New {kind} request (#{lead.get('id')})\n" + "\n".join(bits)


def lead_created(kind, lead):
    """Fire-and-forget. Returns the thread so tests can join it."""
    summary = _summary(kind, lead)
    to = config.COUNSELLING_EMAIL if kind == "counselling" else config.ADMISSIONS_EMAIL
    payload = {"kind": kind, "summary": summary, **{k: v for k, v in lead.items() if k != "consent"}}

    def run():
        _send_email(to, f"[Noah] New {kind} request", summary)
        _post_webhook(payload)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread
