"""
Synthetic Probing — Blueprint Section 3.1.1.

Active health checks against service endpoints.
Signal source: Active health checks
Latency target: < 30 seconds
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
import structlog

from aref.core.models import HealthCheck, ServiceInfo

logger = structlog.get_logger(__name__)


@dataclass
class ProbeTarget:
    service: str
    url: str
    timeout: float = 5.0
    expected_status: int = 200
    _consecutive_failures: int = field(default=0, init=False)
    _last_check: HealthCheck | None = field(default=None, init=False)


class SyntheticProber:
    """
    Active health check system — probes service endpoints
    and reports failures to the detection engine.
    """

    def __init__(self) -> None:
        self._targets: list[ProbeTarget] = []
        self._client: httpx.AsyncClient | None = None
        self._history: list[HealthCheck] = []

    def add_target(self, target: ProbeTarget) -> None:
        self._targets.append(target)

    def add_service(self, info: ServiceInfo) -> None:
        url = f"http://{info.host}:{info.port}{info.health_endpoint}"
        self._targets.append(ProbeTarget(service=info.name, url=url))

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(10.0))
        return self._client

    async def probe(self, target: ProbeTarget) -> HealthCheck:
        client = await self._get_client()
        start = time.perf_counter()

        try:
            resp = await client.get(target.url, timeout=target.timeout)
            latency = (time.perf_counter() - start) * 1000

            if resp.status_code == target.expected_status:
                target._consecutive_failures = 0
                check = HealthCheck(
                    service=target.service,
                    status="healthy",
                    latency_ms=round(latency, 2),
                    details={"status_code": resp.status_code},
                )
            else:
                target._consecutive_failures += 1
                check = HealthCheck(
                    service=target.service,
                    status="degraded",
                    latency_ms=round(latency, 2),
                    details={"status_code": resp.status_code, "expected": target.expected_status},
                )

        except httpx.TimeoutException:
            target._consecutive_failures += 1
            check = HealthCheck(
                service=target.service,
                status="timeout",
                latency_ms=target.timeout * 1000,
                details={"error": "timeout"},
            )
        except httpx.ConnectError:
            target._consecutive_failures += 1
            check = HealthCheck(
                service=target.service,
                status="unreachable",
                latency_ms=0,
                details={"error": "connection_refused"},
            )
        except Exception as e:
            target._consecutive_failures += 1
            check = HealthCheck(
                service=target.service,
                status="error",
                latency_ms=0,
                details={"error": str(e)},
            )

        target._last_check = check
        self._history.append(check)
        return check

    async def probe_all(self) -> list[dict[str, Any]]:
        """Probe all targets concurrently. Returns list of failures."""
        if not self._targets:
            return []

        results = await asyncio.gather(
            *[self.probe(t) for t in self._targets],
            return_exceptions=True,
        )

        failures = []
        for target, result in zip(self._targets, results):
            if isinstance(result, Exception):
                failures.append({
                    "service": target.service,
                    "status": "probe_error",
                    "error": str(result),
                    "consecutive_failures": target._consecutive_failures,
                })
            elif not result.is_healthy:
                failures.append({
                    "service": target.service,
                    "status": result.status,
                    "latency_ms": result.latency_ms,
                    "consecutive_failures": target._consecutive_failures,
                    **result.details,
                })

        return failures

    def get_status(self) -> dict[str, Any]:
        return {
            "targets": [
                {
                    "service": t.service,
                    "url": t.url,
                    "last_status": t._last_check.status if t._last_check else "unknown",
                    "last_latency_ms": t._last_check.latency_ms if t._last_check else 0,
                    "consecutive_failures": t._consecutive_failures,
                }
                for t in self._targets
            ],
            "total_probes": len(self._history),
        }
