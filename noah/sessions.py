"""Per-visitor conversation memory: Redis when REDIS_URL works, otherwise an in-process dict with a TTL."""

import json
import logging
import threading
import time

from . import config

log = logging.getLogger("noah.sessions")

HISTORY_TTL = 7 * 24 * 3600
MEMORY_MAX_SESSIONS = 5000

_redis = None
_redis_tried = False


def _get_redis():
    global _redis, _redis_tried
    if _redis_tried:
        return _redis
    _redis_tried = True
    if not config.REDIS_URL:
        return None
    try:
        import redis  # optional dependency
        client = redis.Redis.from_url(config.REDIS_URL, decode_responses=True, socket_timeout=2, socket_connect_timeout=2)
        client.ping()
        _redis = client
    except Exception as exc:  # noqa: BLE001 - any failure just means "use memory"
        log.warning("Redis unavailable (%s); using in-memory sessions", exc)
        _redis = None
    return _redis


_mem = {}
_mem_lock = threading.Lock()


def _key(kind, sid):
    return f"noah:{kind}:{sid}"


def _mem_get(key):
    with _mem_lock:
        entry = _mem.get(key)
        if not entry:
            return None
        if entry[0] < time.time():
            del _mem[key]
            return None
        return entry[1]


def _mem_set(key, value, ttl):
    with _mem_lock:
        if len(_mem) > MEMORY_MAX_SESSIONS:
            now = time.time()
            for k in [k for k, v in _mem.items() if v[0] < now][:1000] or list(_mem)[:500]:
                _mem.pop(k, None)
        _mem[key] = (time.time() + ttl, value)


def load_history(sid, mode="chat", limit=6):
    key = _key("hist" if mode == "chat" else "hist-" + mode, sid)
    client = _get_redis()
    if client:
        try:
            return [json.loads(x) for x in client.lrange(key, -limit, -1)]
        except Exception:  # noqa: BLE001
            pass
    return list((_mem_get(key) or [])[-limit:])


def save_turn(sid, user_text, bot_text, mode="chat", keep=12):
    key = _key("hist" if mode == "chat" else "hist-" + mode, sid)
    turns = [{"role": "user", "text": user_text[:1500]}, {"role": "assistant", "text": bot_text[:1500]}]
    client = _get_redis()
    if client:
        try:
            pipe = client.pipeline()
            for t in turns:
                pipe.rpush(key, json.dumps(t))
            pipe.ltrim(key, -keep, -1)
            pipe.expire(key, HISTORY_TTL)
            pipe.execute()
            return
        except Exception:  # noqa: BLE001
            pass
    history = (_mem_get(key) or []) + turns
    _mem_set(key, history[-keep:], HISTORY_TTL)


def turn_count(sid, mode="chat"):
    return len(load_history(sid, mode, limit=12))


def clear(sid):
    client = _get_redis()
    if client:
        try:
            client.delete(_key("hist", sid), _key("hist-study", sid))
        except Exception:  # noqa: BLE001
            pass
    with _mem_lock:
        for k in (_key("hist", sid), _key("hist-study", sid)):
            _mem.pop(k, None)


# ---- tiny shared cache (answers to first-turn FAQs) ------------------------------------------
def cache_get(key):
    client = _get_redis()
    if client:
        try:
            raw = client.get("noah:cache:" + key)
            return json.loads(raw) if raw else None
        except Exception:  # noqa: BLE001
            pass
    return _mem_get("cache:" + key)


def cache_set(key, value, ttl=6 * 3600):
    client = _get_redis()
    if client:
        try:
            client.setex("noah:cache:" + key, ttl, json.dumps(value))
            return
        except Exception:  # noqa: BLE001
            pass
    _mem_set("cache:" + key, value, ttl)
