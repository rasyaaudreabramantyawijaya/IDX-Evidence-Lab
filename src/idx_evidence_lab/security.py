"""Response security headers and a small in-memory rate limiter. Pure helpers, no I/O."""
import threading
import time
from typing import Callable

SECURITY_HEADERS = (
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "no-referrer"),
    ("Permissions-Policy", "camera=(), microphone=(), geolocation=()"),
    ("Cross-Origin-Opener-Policy", "same-origin"),
    # Enforced: only directives the current page cannot violate.
    ("Content-Security-Policy", "frame-ancestors 'none'; object-src 'none'; base-uri 'self'"),
    # Report-only: the strict policy the page does not satisfy yet (inline script/style). Observed, never blocked.
    ("Content-Security-Policy-Report-Only",
     "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'"),
)


class RateLimiter:
    """Fixed-window counter per (client, bucket). A limit of 0 disables that bucket."""

    def __init__(self, limits: dict[str, int], window_seconds: float = 60.0,
                 clock: Callable[[], float] = time.monotonic):
        self._limits = dict(limits)
        self._window = window_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._hits: dict[tuple[str, str], tuple[float, int]] = {}

    def check(self, client: str, bucket: str) -> tuple[bool, int]:
        """Return (allowed, retry_after_seconds). Records the hit when allowed."""
        limit = self._limits.get(bucket, 0)
        if limit <= 0:
            return True, 0
        now = self._clock()
        key = (client, bucket)
        with self._lock:
            if len(self._hits) > 10_000:
                self._hits = {k: v for k, v in self._hits.items() if now - v[0] < self._window}
            start, count = self._hits.get(key, (now, 0))
            if now - start >= self._window:
                start, count = now, 0
            if count >= limit:
                return False, max(1, int(start + self._window - now) + 1)
            self._hits[key] = (start, count + 1)
            return True, 0
