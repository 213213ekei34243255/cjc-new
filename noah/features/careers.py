"""Feature 9 - career pathway explorer (static, reviewed data in data/careers.json)."""

import json

from .. import config

_cache = None


def _data():
    global _cache
    if _cache is None:
        _cache = json.loads((config.DATA_DIR / "careers.json").read_text(encoding="utf-8"))
    return _cache


def all_paths():
    return _data()


def path_for(code):
    for p in _data()["paths"]:
        if p["id"].lower() == (code or "").lower():
            return p
    return None
