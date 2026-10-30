"""Tiny in-process sliding-window rate limiter (the app runs one gunicorn worker)."""

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self):
        self._hits = defaultdict(deque)
        self._lock = threading.Lock()
        self._last_sweep = time.monotonic()

    def allow(self, bucket, key, limit, window_seconds):
        """Record a hit and return True while the key is under `limit` hits per window."""
        now = time.monotonic()
        full = f"{bucket}:{key}"
        with self._lock:
            hits = self._hits[full]
            cutoff = now - window_seconds
            while hits and hits[0] < cutoff:
                hits.popleft()
            if len(hits) >= limit:
                return False
            hits.append(now)
            if now - self._last_sweep > 300:
                self._sweep(now)
            return True

    def _sweep(self, now):
        self._last_sweep = now
        for key in [k for k, v in self._hits.items() if not v or v[-1] < now - 7200]:
            del self._hits[key]

    def reset(self):
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()
