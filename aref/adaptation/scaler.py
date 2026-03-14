"""
Auto-Scaler — Blueprint Section 3.3.1.

Horizontal scaling via compute auto-scaling.
Trigger: Load threshold breach
Rollback risk: Low
"""

from __future__ import annotations

import time
from typing import Any

import structlog

from aref.core.metrics import SCALING_EVENTS

logger = structlog.get_logger(__name__)


class AutoScaler:
    """Simulates horizontal scaling of service instances."""

    def __init__(self) -> None:
        self._instances: dict[str, int] = {}  # service -> current instance count
        self._limits: dict[str, dict[str, int]] = {}  # service -> {min, max}
        self._history: list[dict[str, Any]] = []

    def register_service(self, service: str, current: int = 1, min_instances: int = 1, max_instances: int = 10) -> None:
        self._instances[service] = current
        self._limits[service] = {"min": min_instances, "max": max_instances}

    async def scale(self, service: str, direction: str = "up", count: int = 1) -> dict[str, Any]:
        current = self._instances.get(service, 1)
        limits = self._limits.get(service, {"min": 1, "max": 10})

        if direction == "up":
            new_count = min(current + count, limits["max"])
        else:
            new_count = max(current - count, limits["min"])

        self._instances[service] = new_count
        SCALING_EVENTS.labels(direction=direction).inc()

        record = {
            "timestamp": time.time(),
            "service": service,
            "direction": direction,
            "old_count": current,
            "new_count": new_count,
        }
        self._history.append(record)

        logger.info("scaler.scaled", service=service, direction=direction, old=current, new=new_count)
        return record

    def get_instances(self, service: str) -> int:
        return self._instances.get(service, 1)

    def get_status(self) -> dict[str, Any]:
        return {
            "instances": dict(self._instances),
            "limits": dict(self._limits),
            "scaling_history": self._history[-20:],
        }
