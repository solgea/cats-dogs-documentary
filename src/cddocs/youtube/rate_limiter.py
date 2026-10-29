"""Rate limiting middleware for YouTube API calls.

Provides a token-bucket rate limiter to prevent exceeding
YouTube API quota limits per second/minute.
"""

from __future__ import annotations

import time
import threading
from typing import Callable, Optional


class RateLimiter:
    """Token bucket rate limiter.

    Allows up to `max_calls` calls per `period` seconds.
    Thread-safe.
    """

    def __init__(self, max_calls: int, period: float = 60.0):
        self.max_calls = max_calls
        self.period = period
        self._tokens = max_calls
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        if elapsed > 0:
            new_tokens = elapsed * (self.max_calls / self.period)
            self._tokens = min(self.max_calls, self._tokens + new_tokens)
            self._last_refill = now

    def acquire(self, calls: int = 1, block: bool = True, timeout: Optional[float] = None) -> bool:
        """Acquire `calls` tokens from the bucket.

        Args:
            calls: Number of tokens to acquire
            block: If True, wait until tokens are available
            timeout: Maximum seconds to wait (only if block=True)

        Returns:
            True if tokens acquired, False if not (and block=False)
        """
        start = time.monotonic()
        with self._lock:
            while True:
                self._refill()
                if self._tokens >= calls:
                    self._tokens -= calls
                    return True
                if not block:
                    return False
                if timeout is not None and (time.monotonic() - start) >= timeout:
                    return False
                # Wait a bit before retrying
                time.sleep(0.1)

    @property
    def available(self) -> float:
        """Return current available tokens (approximate)."""
        with self._lock:
            self._refill()
            return self._tokens


def rate_limited(
    max_calls: int,
    period: float = 60.0,
    limiter: Optional[RateLimiter] = None,
):
    """Decorator to rate-limit a function.

    Args:
        max_calls: Maximum calls per period
        period: Time period in seconds
        limiter: Shared RateLimiter instance (creates new if None)
    """
    _limiter = limiter or RateLimiter(max_calls, period)

    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            _limiter.acquire(calls=1, block=True)
            return func(*args, **kwargs)
        wrapper._rate_limiter = _limiter
        return wrapper
    return decorator


class QuotaRateLimiter:
    """Combines quota tracking with rate limiting for YouTube API.

    Ensures both:
    1. Rate limit (calls per second/minute)
    2. Quota limit (total cost per day)
    """

    def __init__(
        self,
        max_calls_per_minute: int = 100,
        daily_quota_limit: int = 10000,
    ):
        self.rate_limiter = RateLimiter(max_calls=max_calls_per_minute, period=60.0)
        self.daily_quota_limit = daily_quota_limit
        self._quota_used = 0
        self._lock = threading.Lock()

    def acquire(self, quota_cost: int = 1, block: bool = True) -> bool:
        """Acquire rate token and check quota.

        Args:
            quota_cost: Quota cost of the API call
            block: If True, wait until rate token available

        Returns:
            True if acquired, False otherwise
        """
        if not self.rate_limiter.acquire(calls=1, block=block):
            return False

        with self._lock:
            if self._quota_used + quota_cost > self.daily_quota_limit:
                return False
            self._quota_used += quota_cost
            return True

    @property
    def quota_remaining(self) -> int:
        with self._lock:
            return max(0, self.daily_quota_limit - self._quota_used)

    @property
    def quota_used(self) -> int:
        with self._lock:
            return self._quota_used
