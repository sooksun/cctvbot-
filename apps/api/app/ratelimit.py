"""In-memory fixed-window rate limiter.

Single-process, LAN-scale (the prod compose runs one API container). Not shared
across replicas — swap for Redis if the API is ever scaled horizontally.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict


class RateLimiter:
    def __init__(self, max_attempts: int = 10, window_seconds: float = 60.0) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        """Record an attempt for key; return False when over the limit."""
        ts = time.monotonic() if now is None else now
        cutoff = ts - self.window_seconds
        with self._lock:
            recent = [t for t in self._hits[key] if t >= cutoff]
            if len(recent) >= self.max_attempts:
                self._hits[key] = recent
                return False
            recent.append(ts)
            self._hits[key] = recent
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
