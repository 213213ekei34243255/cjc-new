"""Feature 10 - event assistant. Events live in the database (seeded from data/events.json) so staff
can add dates and links from the widget without a redeploy."""

import json
from datetime import date, datetime, timedelta, timezone

from .. import config
from ..store import StoreError

IST = timezone(timedelta(hours=5, minutes=30))


def seed(store):
    try:
        events = json.loads((config.DATA_DIR / "events.json").read_text(encoding="utf-8"))
        store.seed_events(events)
    except (StoreError, OSError, ValueError):
        pass


def parse_when(value):
    """'2026-11-21' or '2026-11-21T09:30' -> aware datetime in IST, or None."""
    if not value:
        return None
    try:
        if "T" in value:
            return datetime.fromisoformat(value).replace(tzinfo=IST)
        d = date.fromisoformat(value)
        return datetime(d.year, d.month, d.day, tzinfo=IST)
    except ValueError:
        return None


def decorate(event, now=None):
    now = now or datetime.now(IST)
    start = parse_when(event["starts"])
    out = dict(event)
    out["active"] = bool(event["active"])
    out["days_left"] = None
    out["status"] = "dates_tba"
    if start:
        days = (start.date() - now.date()).days
        out["days_left"] = days
        out["status"] = "upcoming" if days > 0 else "today" if days == 0 else "past"
        end = parse_when(event["ends"])
        if end and start.date() <= now.date() <= end.date():
            out["status"] = "happening"
    return out


def list_events(store, now=None):
    seed(store)
    items = [decorate(e, now) for e in store.list_events()]
    order = {"happening": 0, "today": 0, "upcoming": 1, "dates_tba": 2, "past": 3}
    items.sort(key=lambda e: (order[e["status"]], e["days_left"] if e["days_left"] is not None else 9999, e["sort"]))
    return items


def validate_event(data):
    event_id = "".join(ch for ch in (data.get("id") or data.get("title", "").lower().replace(" ", "-")) if ch.isalnum() or ch == "-")[:60]
    if not event_id or not (data.get("title") or "").strip():
        raise ValueError("title is required")
    for key in ("starts", "ends"):
        if data.get(key) and not parse_when(data[key]):
            raise ValueError(f"{key} must look like 2026-11-21 or 2026-11-21T09:30")
    link = (data.get("link_url") or "").strip()
    if link and not link.startswith(("https://", "http://")):
        raise ValueError("link must start with https://")
    return {
        "id": event_id, "title": data["title"].strip()[:120], "blurb": (data.get("blurb") or "")[:500],
        "starts": data.get("starts") or "", "ends": data.get("ends") or "", "location": (data.get("location") or "")[:160],
        "link_label": (data.get("link_label") or "More details")[:60], "link_url": link[:300],
        "contact": (data.get("contact") or "")[:120], "tag": (data.get("tag") or "")[:30],
        "active": bool(data.get("active", True)), "sort": int(data.get("sort", 50)),
    }
