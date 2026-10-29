"""Failed-login limiter (Member 3). In memory, per e-mail address.

Rule: after MAX_FAILS wrong passwords within WINDOW seconds, further logins for that e-mail are refused
(HTTP 429) until the oldest failure is older than the window. A successful login clears the counter.

Limits (documented in Decision.md): the counter lives in this process, so restarting the app clears it, and
it is per e-mail, not per IP address. That is enough for a single-process course project.
"""
import threading
import time


class FailureLimiter:
    def __init__(self, max_fails=5, window_seconds=900):
        self.max_fails = max_fails
        self.window = window_seconds
        self._fails = {}                       # key -> list of failure timestamps (oldest first)
        self._lock = threading.Lock()

    def _prune(self, key, now):
        stamps = [t for t in self._fails.get(key, []) if now - t < self.window]
        if stamps:
            self._fails[key] = stamps
        else:
            self._fails.pop(key, None)
        return stamps

    def retry_after(self, key):
        """Seconds the caller must still wait (0 = allowed)."""
        now = time.time()
        with self._lock:
            stamps = self._prune(key, now)
            if len(stamps) < self.max_fails:
                return 0
            return int(stamps[0] + self.window - now) + 1

    def record(self, key):
        now = time.time()
        with self._lock:
            if len(self._fails) > 10000:       # keep memory bounded
                for k in list(self._fails):
                    self._prune(k, now)
            self._fails.setdefault(key, []).append(now)

    def clear(self, key):
        with self._lock:
            self._fails.pop(key, None)

    def reset_all(self):
        with self._lock:
            self._fails.clear()
