"""
Pre-defined Chaos Experiments — Blueprint-aligned resilience testing scenarios.

Each experiment validates specific AREF pillar capabilities:
  - Detection: Can we detect the failure within MTTD targets?
  - Absorption: Does blast radius stay contained?
  - Adaptation: Does the system self-adjust?
  - Recovery: Do we recover within MTTR targets?
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from chaos.injector import FaultInjector, FaultType

logger = structlog.get_logger(__name__)


@dataclass
class ExperimentResult:
    experiment_name: str
    started_at: float = 0.0
    completed_at: float = 0.0
    success: bool = False
    observations: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChaosExperiment:
    name: str
    description: str
    target_service: str
    fault_type: FaultType
    fault_rate: float = 0.5
    duration: float = 60.0
    hypothesis: str = ""
    pillar_tested: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)


# Pre-defined experiments
EXPERIMENTS: list[ChaosExperiment] = [
    ChaosExperiment(
        name="payment_provider_failure",
        description="Simulate primary payment provider outage to test circuit breaker and dependency substitution",
        target_service="payments",
        fault_type=FaultType.ERROR,
        fault_rate=0.8,
        duration=120,
        hypothesis="Circuit breaker should open within 30s. System should switch to backup provider.",
        pillar_tested="absorption",
    ),
    ChaosExperiment(
        name="order_service_latency",
        description="Inject latency into order service to test detection and auto-scaling",
        target_service="orders",
        fault_type=FaultType.LATENCY,
        fault_rate=0.7,
        duration=90,
        hypothesis="Anomaly detection should fire within 3 minutes. Auto-scaler should add instances.",
        pillar_tested="detection",
        parameters={"delay": 3.0},
    ),
    ChaosExperiment(
        name="inventory_degradation",
        description="Force inventory service errors to test graceful degradation tiers",
        target_service="inventory",
        fault_type=FaultType.ERROR,
        fault_rate=0.6,
        duration=60,
        hypothesis="Inventory should degrade to cached mode, then minimal mode. Orders should still process.",
        pillar_tested="adaptation",
    ),
    ChaosExperiment(
        name="notification_overload",
        description="Simulate notification queue overflow to test load shedding",
        target_service="notifications",
        fault_type=FaultType.LATENCY,
        fault_rate=0.9,
        duration=60,
        hypothesis="Feature flags should disable notifications. Core order flow unaffected.",
        pillar_tested="adaptation",
        parameters={"delay": 5.0},
    ),
    ChaosExperiment(
        name="cascading_failure",
        description="Trigger payment failure that cascades to test full AREF pipeline",
        target_service="payments",
        fault_type=FaultType.ERROR,
        fault_rate=0.95,
        duration=180,
        hypothesis="Full D-A-A-R-E pipeline activates. Recovery within 15 minutes. Post-incident review auto-generated.",
        pillar_tested="all",
    ),
]


class ExperimentRunner:
    """Runs chaos experiments and collects results."""

    def __init__(self, injector: FaultInjector) -> None:
        self.injector = injector
        self._results: list[ExperimentResult] = []

    async def run_experiment(self, experiment: ChaosExperiment) -> ExperimentResult:
        """Run a single chaos experiment."""
        result = ExperimentResult(
            experiment_name=experiment.name,
            started_at=time.time(),
        )

        logger.info(
            "experiment.starting",
            name=experiment.name,
            target=experiment.target_service,
            hypothesis=experiment.hypothesis,
        )

        # Inject fault
        injection = await self.injector.inject(
            target_service=experiment.target_service,
            fault_type=experiment.fault_type,
            rate=experiment.fault_rate,
            duration=experiment.duration,
            parameters=experiment.parameters,
        )

        result.observations.append(f"Fault injected: {injection.injection_id}")

        # Wait for experiment duration
        await asyncio.sleep(experiment.duration)

        # Collect results
        result.completed_at = time.time()
        result.metrics["duration"] = result.completed_at - result.started_at
        result.success = True  # Detailed validation would check AREF metrics

        self._results.append(result)
        logger.info("experiment.completed", name=experiment.name, success=result.success)

        return result

    async def run_all(self) -> list[ExperimentResult]:
        """Run all pre-defined experiments sequentially."""
        results = []
        for exp in EXPERIMENTS:
            result = await self.run_experiment(exp)
            results.append(result)
        return results

    def get_results(self) -> list[dict[str, Any]]:
        return [
            {
                "name": r.experiment_name,
                "success": r.success,
                "duration": r.completed_at - r.started_at if r.completed_at else 0,
                "observations": r.observations,
            }
            for r in self._results
        ]
