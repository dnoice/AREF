"""
Rate Limiter — Blueprint Section 3.2.1.

Token bucket algorithm for preventing resource exhaustion under unexpected load.
Supports per-service and per-endpoint rate limiting.
"""

from __future__ import annotations

import time
from typing import Any

import structlog

from aref.core.metrics import RATE_LIMIT_REJECTED

logger = structlog.get_logger(__name__)


class RateLimitExceeded(Exception):
    """Raised when a request exceeds the rate limit."""
    pass


class TokenBucket:
    """
    Token bucket rate limiter.
    Allows burst traffic up to bucket capacity while enforcing sustained rate.
    """

    def __init__(
        self,
        name: str,
        rate: float = 100.0,     # tokens per second
        capacity: int = 20,       # burst capacity
    ) -> None:
        self.name = name
        self.rate = rate
        self.capacity = capacity
        self._tokens = float(capacity)
        self._last_refill = time.monotonic()
        self._total_allowed = 0
        self._total_rejected = 0

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
        self._last_refill = now

    def allow(self) -> bool:
        self._refill()
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            self._total_allowed += 1
            return True
        self._total_rejected += 1
        return False

    def consume(self, service: str = "") -> None:
        """Consume a token or raise RateLimitExceeded."""
        if not self.allow():
            RATE_LIMIT_REJECTED.labels(service=service or self.name).inc()
            raise RateLimitExceeded(
                f"Rate limit exceeded for '{self.name}' — "
                f"{self.rate} req/s, burst {self.capacity}"
            )

    @property
    def available_tokens(self) -> float:
        self._refill()
        return self._tokens

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "rate_per_second": self.rate,
            "burst_capacity": self.capacity,
            "available_tokens": round(self.available_tokens, 1),
            "total_allowed": self._total_allowed,
            "total_rejected": self._total_rejected,
        }


class RateLimiterManager:
    """Manages rate limiters across services and endpoints."""

    def __init__(self) -> None:
        self._limiters: dict[str, TokenBucket] = {}

    def create(self, name: str, rate: float = 100.0, capacity: int = 20) -> TokenBucket:
        limiter = TokenBucket(name=name, rate=rate, capacity=capacity)
        self._limiters[name] = limiter
        return limiter

    def get(self, name: str) -> TokenBucket | None:
        return self._limiters.get(name)

    def check(self, name: str) -> bool:
        limiter = self._limiters.get(name)
        if limiter is None:
            return True  # No limiter = no limit
        return limiter.allow()

    def get_status(self) -> dict[str, Any]:
        return {
            "total": len(self._limiters),
            "limiters": {name: l.to_dict() for name, l in self._limiters.items()},
        }
