"""
Bulkhead Pattern — Blueprint Section 3.2.1.

Partitions system resources so failure in one partition doesn't propagate.
Implements semaphore-based concurrent call limiting per dependency.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Coroutine, TypeVar

import structlog

logger = structlog.get_logger(__name__)

T = TypeVar("T")


class BulkheadFullError(Exception):
    """Raised when a bulkhead partition has no available capacity."""
    pass


class Bulkhead:
    """
    Limits concurrent access to a resource partition.
    Prevents one failing dependency from consuming all system resources.
    """

    def __init__(
        self,
        name: str,
        max_concurrent: int = 50,
        max_queue: int = 100,
        timeout: float = 10.0,
    ) -> None:
        self.name = name
        self.max_concurrent = max_concurrent
        self.max_queue = max_queue
        self.timeout = timeout

        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._active = 0
        self._queued = 0
        self._rejected = 0
        self._total = 0

    async def execute(self, fn: Callable[..., Coroutine[Any, Any, T]], *args: Any, **kwargs: Any) -> T:
        """Execute a function within the bulkhead partition."""
        if self._queued >= self.max_queue:
            self._rejected += 1
            raise BulkheadFullError(
                f"Bulkhead '{self.name}' is full — "
                f"{self._active} active, {self._queued} queued"
            )

        self._queued += 1
        try:
            acquired = await asyncio.wait_for(
                self._semaphore.acquire(), timeout=self.timeout
            )
        except asyncio.TimeoutError:
            self._queued -= 1
            self._rejected += 1
            raise BulkheadFullError(f"Bulkhead '{self.name}' timed out waiting for capacity")

        self._queued -= 1
        self._active += 1
        self._total += 1

        try:
            return await fn(*args, **kwargs)
        finally:
            self._active -= 1
            self._semaphore.release()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "max_concurrent": self.max_concurrent,
            "active": self._active,
            "queued": self._queued,
            "rejected": self._rejected,
            "total_calls": self._total,
            "utilization_pct": round((self._active / self.max_concurrent) * 100, 1),
        }


class BulkheadManager:
    """Manages bulkhead partitions across all service dependencies."""

    def __init__(self) -> None:
        self._bulkheads: dict[str, Bulkhead] = {}

    def create(self, name: str, max_concurrent: int = 50, **kwargs: Any) -> Bulkhead:
        bulkhead = Bulkhead(name=name, max_concurrent=max_concurrent, **kwargs)
        self._bulkheads[name] = bulkhead
        return bulkhead

    def get(self, name: str) -> Bulkhead | None:
        return self._bulkheads.get(name)

    def get_status(self) -> dict[str, Any]:
        return {
            "total": len(self._bulkheads),
            "partitions": {name: b.to_dict() for name, b in self._bulkheads.items()},
        }
