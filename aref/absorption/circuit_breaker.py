"""
Circuit Breaker Pattern — Blueprint Section 3.2.1.

States: CLOSED -> OPEN -> HALF_OPEN -> CLOSED
Prevents cascading failures by halting calls to failing dependencies.
Integrated with Prometheus metrics for real-time state visibility.
"""

from __future__ import annotations

import asyncio
import time
from enum import Enum
from typing import Any, Callable, Coroutine, TypeVar

import structlog

from aref.core.events import Event, EventCategory, EventSeverity, get_event_bus
from aref.core.metrics import CIRCUIT_BREAKER_STATE

logger = structlog.get_logger(__name__)

T = TypeVar("T")


class CircuitState(Enum):
    CLOSED = 0       # Normal operation — requests pass through
    HALF_OPEN = 1    # Testing recovery — limited requests allowed
    OPEN = 2         # Failure detected — all requests blocked


class CircuitBreakerError(Exception):
    """Raised when a call is blocked by an open circuit breaker."""
    pass


class CircuitBreaker:
    """
    Circuit breaker with configurable thresholds aligned with AREF absorption config.

    Tracks consecutive failures and transitions between states:
      CLOSED: All requests pass. Track failures.
      OPEN: All requests fail-fast. Wait for recovery timeout.
      HALF_OPEN: Allow limited requests. If they succeed, close. If they fail, reopen.
    """

    def __init__(
        self,
        name: str,
        service: str,
        dependency: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 3,
    ) -> None:
        self.name = name
        self.service = service
        self.dependency = dependency
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._last_failure_time: float = 0
        self._state_changed_at: float = time.time()
        self._total_blocked = 0

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if time.time() - self._last_failure_time >= self.recovery_timeout:
                self._transition(CircuitState.HALF_OPEN)
        return self._state

    def _transition(self, new_state: CircuitState) -> None:
        old = self._state
        self._state = new_state
        self._state_changed_at = time.time()

        CIRCUIT_BREAKER_STATE.labels(
            service=self.service, dependency=self.dependency
        ).set(new_state.value)

        logger.info(
            "circuit_breaker.transition",
            breaker=self.name,
            old_state=old.name,
            new_state=new_state.name,
        )

        if new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0
        elif new_state == CircuitState.CLOSED:
            self._failure_count = 0

    async def call(self, fn: Callable[..., Coroutine[Any, Any, T]], *args: Any, **kwargs: Any) -> T:
        """Execute a function through the circuit breaker."""
        current = self.state

        if current == CircuitState.OPEN:
            self._total_blocked += 1
            raise CircuitBreakerError(
                f"Circuit breaker '{self.name}' is OPEN — "
                f"calls to {self.dependency} are blocked"
            )

        if current == CircuitState.HALF_OPEN:
            if self._half_open_calls >= self.half_open_max_calls:
                raise CircuitBreakerError(
                    f"Circuit breaker '{self.name}' is HALF_OPEN — "
                    f"max test calls ({self.half_open_max_calls}) reached"
                )
            self._half_open_calls += 1

        try:
            result = await fn(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    def _on_success(self) -> None:
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.half_open_max_calls:
                self._transition(CircuitState.CLOSED)
        elif self._state == CircuitState.CLOSED:
            self._failure_count = 0

    def _on_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._state == CircuitState.HALF_OPEN:
            self._transition(CircuitState.OPEN)
        elif self._failure_count >= self.failure_threshold:
            self._transition(CircuitState.OPEN)

    def reset(self) -> None:
        self._transition(CircuitState.CLOSED)
        self._failure_count = 0
        self._success_count = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "service": self.service,
            "dependency": self.dependency,
            "state": self.state.name,
            "failure_count": self._failure_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
            "total_blocked": self._total_blocked,
            "state_changed_at": self._state_changed_at,
        }


class CircuitBreakerRegistry:
    """Manages all circuit breakers across the platform."""

    def __init__(self) -> None:
        self._breakers: dict[str, CircuitBreaker] = {}

    def register(self, breaker: CircuitBreaker) -> None:
        self._breakers[breaker.name] = breaker

    def get(self, name: str) -> CircuitBreaker | None:
        return self._breakers.get(name)

    def get_all(self) -> list[CircuitBreaker]:
        return list(self._breakers.values())

    def get_open_breakers(self) -> list[CircuitBreaker]:
        return [b for b in self._breakers.values() if b.state == CircuitState.OPEN]

    def get_status(self) -> dict[str, Any]:
        return {
            "total": len(self._breakers),
            "open": len(self.get_open_breakers()),
            "breakers": {name: b.to_dict() for name, b in self._breakers.items()},
        }


# Singleton registry
_registry: CircuitBreakerRegistry | None = None


def get_circuit_breaker_registry() -> CircuitBreakerRegistry:
    global _registry
    if _registry is None:
        _registry = CircuitBreakerRegistry()
    return _registry
