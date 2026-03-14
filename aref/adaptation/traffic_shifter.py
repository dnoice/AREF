"""
Traffic Shifting — Blueprint Section 3.3.1.

Redirects traffic to healthy regions/instances when degradation is detected.
Trigger: Regional health degradation
Rollback risk: Medium
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from aref.core.metrics import TRAFFIC_SHIFTED

logger = structlog.get_logger(__name__)


@dataclass
class TrafficRoute:
    target: str
    weight: int = 100  # percentage
    healthy: bool = True


class TrafficShifter:
    """Manages traffic distribution across service instances/regions."""

    def __init__(self) -> None:
        self._routes: dict[str, list[TrafficRoute]] = {}
        self._history: list[dict[str, Any]] = []

    def register_routes(self, service: str, routes: list[TrafficRoute]) -> None:
        self._routes[service] = routes

    def shift(self, from_target: str, to_target: str, weight: int = 100) -> None:
        """Shift traffic weight from one target to another."""
        TRAFFIC_SHIFTED.labels(from_region=from_target, to_region=to_target).inc()
        self._history.append({
            "timestamp": time.time(),
            "from": from_target,
            "to": to_target,
            "weight": weight,
        })
        logger.info("traffic.shifted", from_=from_target, to=to_target, weight=weight)

    def mark_unhealthy(self, service: str, target: str) -> None:
        routes = self._routes.get(service, [])
        for route in routes:
            if route.target == target:
                route.healthy = False
                route.weight = 0
        self._redistribute(service)

    def mark_healthy(self, service: str, target: str) -> None:
        routes = self._routes.get(service, [])
        for route in routes:
            if route.target == target:
                route.healthy = True
        self._redistribute(service)

    def _redistribute(self, service: str) -> None:
        routes = self._routes.get(service, [])
        healthy = [r for r in routes if r.healthy]
        if not healthy:
            return
        weight_each = 100 // len(healthy)
        remainder = 100 % len(healthy)
        for i, route in enumerate(healthy):
            route.weight = weight_each + (1 if i < remainder else 0)
        for route in routes:
            if not route.healthy:
                route.weight = 0

    def get_routes(self, service: str) -> list[dict[str, Any]]:
        return [
            {"target": r.target, "weight": r.weight, "healthy": r.healthy}
            for r in self._routes.get(service, [])
        ]

    def get_status(self) -> dict[str, Any]:
        return {
            "services": {
                svc: self.get_routes(svc) for svc in self._routes
            },
            "shift_history": self._history[-20:],
        }
