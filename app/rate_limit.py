"""Small in-process sliding-window limits for the single-worker prototype."""

from collections import deque
from threading import Lock
from time import monotonic


class RequestRateLimiter:
    def __init__(self, *, max_requests: int = 120, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = {}
        self._lock = Lock()

    def allow(self, key: str, *, now: float | None = None) -> bool:
        current = monotonic() if now is None else now
        cutoff = current - self.window_seconds
        with self._lock:
            events = self._events.setdefault(key, deque())
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.max_requests:
                return False
            events.append(current)
            if len(self._events) > 10_000:
                stale = [
                    address
                    for address, timestamps in self._events.items()
                    if not timestamps or timestamps[-1] <= cutoff
                ]
                for address in stale:
                    self._events.pop(address, None)
                while len(self._events) > 10_000:
                    self._events.pop(next(iter(self._events)))
            return True
