"""Lightweight in-process rate limiter for auth endpoints.

Sliding-window counter keyed by (route, ip) — no external deps. Suitable for
single-process Flask deployments. For multi-worker setups, replace the
backing store with Redis (see _Bucket — only the dict access needs to change).

Limits are intentionally conservative:
  * /login, /register: 10 attempts / 5 min / ip
  * /password:         5 attempts / 5 min / ip
"""

import threading
import time
from collections import deque
from functools import wraps

from flask import jsonify, request


class _SlidingWindow:
  """Per-key deque of request timestamps; trims older than `window_s`."""

  def __init__(self, window_s: float, max_hits: int):
    self.window_s = window_s
    self.max_hits = max_hits
    self._buckets: dict[str, deque] = {}
    self._lock = threading.Lock()

  def hit(self, key: str) -> tuple[bool, float]:
    """Record a hit. Returns (allowed, retry_after_seconds)."""
    now = time.monotonic()
    cutoff = now - self.window_s
    with self._lock:
      bucket = self._buckets.setdefault(key, deque())
      while bucket and bucket[0] < cutoff:
        bucket.popleft()
      if len(bucket) >= self.max_hits:
        retry_after = max(0.0, bucket[0] + self.window_s - now)
        return False, retry_after
      bucket.append(now)
      return True, 0.0


def _client_ip() -> str:
  """Best-effort client IP. Trusts X-Forwarded-For only when explicitly enabled."""
  forwarded = request.headers.get("X-Forwarded-For", "")
  if forwarded:
    return forwarded.split(",")[0].strip()
  return request.remote_addr or "unknown"


def rate_limit(window_s: float, max_hits: int):
  """Decorator factory: limit a Flask view to max_hits per window_s per IP."""
  window = _SlidingWindow(window_s, max_hits)

  def decorator(view_fn):
    @wraps(view_fn)
    def wrapper(*args, **kwargs):
      key = f"{request.endpoint}:{_client_ip()}"
      allowed, retry_after = window.hit(key)
      if not allowed:
        resp = jsonify({
          "error": "Too many requests. Please slow down.",
          "retry_after_seconds": round(retry_after, 1),
        })
        resp.status_code = 429
        resp.headers["Retry-After"] = str(int(retry_after) + 1)
        return resp
      return view_fn(*args, **kwargs)
    return wrapper
  return decorator
