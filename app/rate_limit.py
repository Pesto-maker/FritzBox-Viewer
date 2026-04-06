"""
Simple in-memory rate limiter (no extra dependency).

Usage:
    limiter = RateLimiter(calls=1, period=30)   # max 1 call per 30s

    if not limiter.allow():
        return JSONResponse({"status": "error", "message": "..."}, status_code=429)
"""

import time
import threading


class RateLimiter:
    """Token-bucket style limiter — single-user app, so no per-IP tracking needed."""

    def __init__(self, calls: int = 1, period: float = 30):
        self._calls = calls
        self._period = period
        self._timestamps: list[float] = []
        self._lock = threading.Lock()

    def allow(self) -> bool:
        now = time.monotonic()
        with self._lock:
            # Drop expired timestamps
            self._timestamps = [t for t in self._timestamps if now - t < self._period]
            if len(self._timestamps) >= self._calls:
                return False
            self._timestamps.append(now)
            return True

    @property
    def retry_after(self) -> int:
        """Seconds until the next call would be allowed."""
        if not self._timestamps:
            return 0
        oldest = min(self._timestamps)
        return max(1, int(self._period - (time.monotonic() - oldest)) + 1)
