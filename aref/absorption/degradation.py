"""
Graceful Degradation Manager — Blueprint Section 2.3 / 3.2.1.

"Systems should fail partially rather than catastrophically.
 Maintain core functions under stress while shedding non-essential load.
 Define explicit degradation tiers for every service."
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

import structlog

from aref.core.events import Event, EventCategory, EventSeverity, get_event_bus

logger = structlog.get_logger(__name__)


class DegradationLevel(IntEnum):
    FULL = 0          # All features operational
    REDUCED = 1       # Non-essential features disabled
    MINIMAL = 2       # Core functionality only
    EMERGENCY = 3     # Read-only / static responses


@dataclass
class DegradationTier:
    level: DegradationLevel
    name: str
    description: str
    disabled_features: list[str] = field(default_factory=list)
    reduced_capacity_pct: float = 100.0


@dataclass
class ServiceDegradation:
    """Degradation configuration for a single service."""
    service: str
    current_level: DegradationLevel = DegradationLevel.FULL
    tiers: list[DegradationTier] = field(default_factory=list)
    _history: list[dict[str, Any]] = field(default_factory=list, init=False)

    def set_level(self, level: DegradationLevel) -> DegradationLevel:
        old = self.current_level
        self.current_level = level
        self._history.append({
            "timestamp": time.time(),
            "old_level": old.name,
            "new_level": level.name,
        })
        return old


class DegradationManager:
    """Manages graceful degradation across all services."""

    def __init__(self) -> None:
        self._services: dict[str, ServiceDegradation] = {}
        self.bus = get_event_bus()

    def register_service(self, config: ServiceDegradation) -> None:
        self._services[config.service] = config

    async def degrade(self, service: str, level: DegradationLevel, reason: str = "") -> bool:
        config = self._services.get(service)
        if not config:
            return False

        old = config.set_level(level)

        await self.bus.publish(Event(
            category=EventCategory.ABSORPTION,
            event_type="degradation_changed",
            severity=EventSeverity.WARNING if level > DegradationLevel.FULL else EventSeverity.INFO,
            source="degradation_manager",
            payload={
                "service": service,
                "old_level": old.name,
                "new_level": level.name,
                "reason": reason,
            },
        ))

        logger.info(
            "degradation.changed",
            service=service,
            old=old.name,
            new=level.name,
            reason=reason,
        )
        return True

    async def restore(self, service: str) -> bool:
        return await self.degrade(service, DegradationLevel.FULL, reason="restored")

    def get_level(self, service: str) -> DegradationLevel:
        config = self._services.get(service)
        return config.current_level if config else DegradationLevel.FULL

    def get_status(self) -> dict[str, Any]:
        return {
            service: {
                "current_level": config.current_level.name,
                "level_value": config.current_level.value,
                "tiers_defined": len(config.tiers),
                "changes": len(config._history),
            }
            for service, config in self._services.items()
        }
