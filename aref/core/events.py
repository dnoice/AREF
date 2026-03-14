"""
AREF Event Bus — Async, in-process publish/subscribe for inter-pillar communication.

Supports both sync and async handlers, wildcard subscriptions, and event history
for the Evolution pillar's post-incident timeline reconstruction.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine

import structlog

logger = structlog.get_logger(__name__)


class EventSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class EventCategory(str, Enum):
    DETECTION = "detection"
    ABSORPTION = "absorption"
    ADAPTATION = "adaptation"
    RECOVERY = "recovery"
    EVOLUTION = "evolution"
    SYSTEM = "system"
    CHAOS = "chaos"


@dataclass
class Event:
    category: EventCategory
    event_type: str
    severity: EventSeverity = EventSeverity.INFO
    payload: dict[str, Any] = field(default_factory=dict)
    source: str = ""
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: float = field(default_factory=time.time)
    correlation_id: str | None = None

    @property
    def topic(self) -> str:
        return f"{self.category.value}.{self.event_type}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "category": self.category.value,
            "event_type": self.event_type,
            "severity": self.severity.value,
            "source": self.source,
            "timestamp": self.timestamp,
            "correlation_id": self.correlation_id,
            "payload": self.payload,
        }


Handler = Callable[[Event], Coroutine[Any, Any, None]] | Callable[[Event], None]


class EventBus:
    """
    In-process async event bus with topic-based pub/sub.

    Topic format: "category.event_type"
    Wildcard: "category.*" subscribes to all events in a category
              "*" subscribes to all events
    """

    def __init__(self, history_limit: int = 10_000) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self._history: list[Event] = []
        self._history_limit = history_limit
        self._lock = asyncio.Lock()

    def subscribe(self, topic: str, handler: Handler) -> None:
        self._handlers[topic].append(handler)
        logger.debug("event_bus.subscribe", topic=topic, handler=handler.__qualname__)

    def unsubscribe(self, topic: str, handler: Handler) -> None:
        if topic in self._handlers:
            self._handlers[topic] = [h for h in self._handlers[topic] if h is not handler]

    async def publish(self, event: Event) -> None:
        async with self._lock:
            self._history.append(event)
            if len(self._history) > self._history_limit:
                self._history = self._history[-self._history_limit:]

        # Collect matching handlers: exact topic, category wildcard, global wildcard
        handlers: list[Handler] = []
        handlers.extend(self._handlers.get(event.topic, []))
        handlers.extend(self._handlers.get(f"{event.category.value}.*", []))
        handlers.extend(self._handlers.get("*", []))

        for handler in handlers:
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                logger.exception(
                    "event_bus.handler_error",
                    topic=event.topic,
                    handler=handler.__qualname__,
                    event_id=event.event_id,
                )

    def get_history(
        self,
        category: EventCategory | None = None,
        since: float | None = None,
        severity: EventSeverity | None = None,
        limit: int = 100,
    ) -> list[Event]:
        events = self._history
        if category:
            events = [e for e in events if e.category == category]
        if since:
            events = [e for e in events if e.timestamp >= since]
        if severity:
            events = [e for e in events if e.severity == severity]
        return events[-limit:]

    def get_timeline(self, correlation_id: str) -> list[Event]:
        return sorted(
            [e for e in self._history if e.correlation_id == correlation_id],
            key=lambda e: e.timestamp,
        )

    def clear_history(self) -> None:
        self._history.clear()


# Singleton
_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus


def reset_event_bus() -> None:
    global _bus
    _bus = None
