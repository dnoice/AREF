"""
Fault Injector — Injects controlled failures into the microservice platform.

Types of faults:
  - Latency injection: Add artificial delay
  - Error injection: Return errors at a configurable rate
  - Crash injection: Simulate service crash
  - Resource exhaustion: Simulate CPU/memory pressure
  - Network partition: Block communication between services
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx
import structlog

from aref.core.events import Event, EventCategory, EventSeverity, get_event_bus

logger = structlog.get_logger(__name__)


class FaultType(str, Enum):
    LATENCY = "latency"
    ERROR = "error"
    CRASH = "crash"
    TIMEOUT = "timeout"
    RESOURCE_EXHAUSTION = "resource_exhaustion"


@dataclass
class FaultInjection:
    """A configured fault injection targeting a specific service."""
    injection_id: str = ""
    target_service: str = ""
    fault_type: FaultType = FaultType.ERROR
    rate: float = 0.5       # 0.0-1.0 probability
    duration: float = 60.0  # seconds
    parameters: dict[str, Any] = field(default_factory=dict)
    started_at: float = 0.0
    ended_at: float | None = None
    safe: bool = True  # safety bounds enforced

    @property
    def is_active(self) -> bool:
        if self.ended_at:
            return False
        if self.started_at == 0:
            return False
        return (time.time() - self.started_at) < self.duration


import os
_docker = os.environ.get("AREF_ENVIRONMENT") == "docker"
SERVICE_URLS = {
    "orders": f"http://{'orders' if _docker else 'localhost'}:8001",
    "payments": f"http://{'payments' if _docker else 'localhost'}:8002",
    "inventory": f"http://{'inventory' if _docker else 'localhost'}:8003",
    "notifications": f"http://{'notifications' if _docker else 'localhost'}:8004",
}


class FaultInjector:
    """
    Injects controlled faults into microservices for resilience testing.
    All injections have safety bounds: max rate, max duration, and auto-rollback.
    """

    def __init__(self) -> None:
        self._active_injections: dict[str, FaultInjection] = {}
        self._history: list[FaultInjection] = []
        self._counter = 0
        self.bus = get_event_bus()
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(10.0))
        return self._client

    async def inject(
        self,
        target_service: str,
        fault_type: FaultType,
        rate: float = 0.5,
        duration: float = 60.0,
        parameters: dict[str, Any] | None = None,
    ) -> FaultInjection:
        """Inject a fault into a target service."""
        # Safety bounds
        rate = min(rate, 0.9)  # Never exceed 90% failure rate
        duration = min(duration, 300.0)  # Max 5 minutes

        self._counter += 1
        injection = FaultInjection(
            injection_id=f"CHAOS-{self._counter:04d}",
            target_service=target_service,
            fault_type=fault_type,
            rate=rate,
            duration=duration,
            parameters=parameters or {},
            started_at=time.time(),
        )

        # Send chaos enable request to the target service
        url = SERVICE_URLS.get(target_service)
        if url:
            client = await self._get_client()
            try:
                await client.post(f"{url}/chaos/enable", json={
                    "type": fault_type.value,
                    "rate": rate,
                    "delay": parameters.get("delay", 2.0) if parameters else 2.0,
                })
            except Exception as e:
                logger.error("chaos.inject_failed", target=target_service, error=str(e))

        self._active_injections[injection.injection_id] = injection

        await self.bus.publish(Event(
            category=EventCategory.CHAOS,
            event_type="fault_injected",
            severity=EventSeverity.WARNING,
            source="chaos_injector",
            payload={
                "injection_id": injection.injection_id,
                "target": target_service,
                "fault_type": fault_type.value,
                "rate": rate,
                "duration": duration,
            },
        ))

        logger.info("chaos.injected", injection_id=injection.injection_id, target=target_service, type=fault_type.value)

        # Schedule auto-rollback
        asyncio.create_task(self._auto_rollback(injection))

        return injection

    async def _auto_rollback(self, injection: FaultInjection) -> None:
        """Automatically roll back a fault injection after its duration expires."""
        await asyncio.sleep(injection.duration)
        await self.rollback(injection.injection_id)

    async def rollback(self, injection_id: str) -> bool:
        """Roll back a fault injection."""
        injection = self._active_injections.pop(injection_id, None)
        if not injection:
            return False

        injection.ended_at = time.time()
        self._history.append(injection)

        # Disable chaos on the target service
        url = SERVICE_URLS.get(injection.target_service)
        if url:
            client = await self._get_client()
            try:
                await client.post(f"{url}/chaos/disable")
            except Exception:
                logger.error("chaos.rollback_failed", target=injection.target_service)

        await self.bus.publish(Event(
            category=EventCategory.CHAOS,
            event_type="fault_rolled_back",
            source="chaos_injector",
            payload={"injection_id": injection_id, "target": injection.target_service},
        ))

        logger.info("chaos.rolled_back", injection_id=injection_id)
        return True

    async def rollback_all(self) -> int:
        """Emergency rollback of all active injections."""
        count = 0
        for injection_id in list(self._active_injections.keys()):
            if await self.rollback(injection_id):
                count += 1
        return count

    def get_active(self) -> list[dict[str, Any]]:
        return [
            {
                "injection_id": inj.injection_id,
                "target": inj.target_service,
                "fault_type": inj.fault_type.value,
                "rate": inj.rate,
                "elapsed": time.time() - inj.started_at,
                "remaining": max(0, inj.duration - (time.time() - inj.started_at)),
            }
            for inj in self._active_injections.values()
            if inj.is_active
        ]

    def get_status(self) -> dict[str, Any]:
        return {
            "active_injections": len(self._active_injections),
            "total_injections": len(self._history) + len(self._active_injections),
            "active": self.get_active(),
        }
