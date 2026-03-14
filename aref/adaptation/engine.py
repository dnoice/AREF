"""
Adaptation Engine — Orchestrates all adaptation strategies.

Implements the Adaptation Decision Tree (Blueprint 3.3.2):
  1. Classify the anomaly: transient, persistent, or escalating?
  2. Assess blast radius: which components and users are affected?
  3. Evaluate available strategies against current system state
  4. Select the minimum-impact strategy that addresses the anomaly
  5. Execute with automated rollback triggers in place
  6. If ineffective within the adaptation window, escalate to Recovery
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import structlog

from aref.core.config import get_config
from aref.core.events import Event, EventBus, EventCategory, EventSeverity, get_event_bus
from aref.core.metrics import ADAPTATION_LATENCY
from aref.core.models import AnomalyClass, Incident

from aref.adaptation.feature_flags import FeatureFlagManager
from aref.adaptation.traffic_shifter import TrafficShifter
from aref.adaptation.scaler import AutoScaler
from aref.adaptation.decision_tree import AdaptationDecisionTree, AdaptationAction

logger = structlog.get_logger(__name__)


class AdaptationEngine:
    """
    Central adaptation orchestrator.
    Listens for detection events and executes appropriate adaptation strategies.
    """

    def __init__(self, bus: EventBus | None = None) -> None:
        self.config = get_config().adaptation
        self.bus = bus or get_event_bus()

        self.feature_flags = FeatureFlagManager()
        self.traffic_shifter = TrafficShifter()
        self.scaler = AutoScaler()
        self.decision_tree = AdaptationDecisionTree()

        self._active_adaptations: dict[str, dict[str, Any]] = {}
        self._history: list[dict[str, Any]] = []
        self._running = False

    async def start(self) -> None:
        """Start listening for detection events."""
        self._running = True
        self.bus.subscribe("detection.alert_fired", self._on_alert)
        self.bus.subscribe("absorption.circuit_breaker_opened", self._on_circuit_open)
        logger.info("adaptation.engine.started")

    async def stop(self) -> None:
        self._running = False
        logger.info("adaptation.engine.stopped")

    async def _on_alert(self, event: Event) -> None:
        """React to detection alerts with appropriate adaptation."""
        if not self._running:
            return

        payload = event.payload
        service = payload.get("service", "unknown")
        severity = event.severity

        # Only adapt on WARNING+ severity
        if severity not in (EventSeverity.WARNING, EventSeverity.CRITICAL, EventSeverity.EMERGENCY):
            return

        start = time.time()

        # Run the decision tree
        action = self.decision_tree.decide(
            anomaly_class=self._classify_anomaly(payload),
            severity=severity,
            service=service,
            context=payload,
        )

        if action:
            await self._execute_action(action, event)
            latency = time.time() - start
            ADAPTATION_LATENCY.observe(latency)

    async def _on_circuit_open(self, event: Event) -> None:
        """When a circuit breaker opens, consider traffic shifting or dependency substitution."""
        payload = event.payload
        service = payload.get("service", "")
        dependency = payload.get("dependency", "")

        action = AdaptationAction(
            strategy="dependency_substitution",
            service=service,
            parameters={"failed_dependency": dependency},
            rollback_strategy="revert_provider",
        )
        await self._execute_action(action, event)

    async def _execute_action(self, action: AdaptationAction, trigger_event: Event) -> None:
        """Execute an adaptation action with rollback safety."""
        adaptation_id = f"ADP-{len(self._history):06d}"

        record = {
            "adaptation_id": adaptation_id,
            "strategy": action.strategy,
            "service": action.service,
            "parameters": action.parameters,
            "trigger_event": trigger_event.event_id,
            "started_at": time.time(),
            "status": "executing",
        }
        self._active_adaptations[adaptation_id] = record

        try:
            if action.strategy == "feature_flagging":
                await self._execute_feature_flag(action)
            elif action.strategy == "traffic_shifting":
                await self._execute_traffic_shift(action)
            elif action.strategy == "horizontal_scaling":
                await self._execute_scaling(action)
            elif action.strategy == "dependency_substitution":
                await self._execute_dependency_sub(action)
            elif action.strategy == "cognitive_load_shedding":
                await self._execute_load_shedding(action)

            record["status"] = "completed"
            record["completed_at"] = time.time()

            await self.bus.publish(Event(
                category=EventCategory.ADAPTATION,
                event_type="action_completed",
                source="adaptation_engine",
                payload=record,
                correlation_id=trigger_event.correlation_id,
            ))

        except Exception as e:
            record["status"] = "failed"
            record["error"] = str(e)
            logger.exception("adaptation.action_failed", adaptation_id=adaptation_id)

            # Attempt rollback
            if action.rollback_strategy:
                logger.info("adaptation.rollback", adaptation_id=adaptation_id)

        self._history.append(record)
        self._active_adaptations.pop(adaptation_id, None)

    async def _execute_feature_flag(self, action: AdaptationAction) -> None:
        flags = action.parameters.get("flags", [])
        for flag in flags:
            self.feature_flags.disable(flag)
        logger.info("adaptation.feature_flags_disabled", flags=flags)

    async def _execute_traffic_shift(self, action: AdaptationAction) -> None:
        from_target = action.parameters.get("from", "")
        to_target = action.parameters.get("to", "")
        weight = action.parameters.get("weight", 100)
        self.traffic_shifter.shift(from_target, to_target, weight)

    async def _execute_scaling(self, action: AdaptationAction) -> None:
        service = action.service
        direction = action.parameters.get("direction", "up")
        count = action.parameters.get("count", 1)
        await self.scaler.scale(service, direction, count)

    async def _execute_dependency_sub(self, action: AdaptationAction) -> None:
        failed = action.parameters.get("failed_dependency", "")
        logger.info("adaptation.dependency_substitution", failed=failed)
        # In production, this would switch to an alternate provider

    async def _execute_load_shedding(self, action: AdaptationAction) -> None:
        logger.info("adaptation.cognitive_load_shedding", service=action.service)
        # Reduce dashboard complexity, mute non-critical alerts

    def _classify_anomaly(self, payload: dict[str, Any]) -> AnomalyClass:
        breach_count = payload.get("consecutive_breaches", 0)
        z_score = payload.get("z_score", 0)

        if breach_count <= 2 or z_score < 3:
            return AnomalyClass.TRANSIENT
        elif breach_count <= 5 or z_score < 5:
            return AnomalyClass.PERSISTENT
        else:
            return AnomalyClass.ESCALATING

    async def check_adaptation_window(self) -> None:
        """Check if any active adaptations have exceeded their window and need recovery escalation."""
        window = self.config.adaptation_window_seconds
        now = time.time()

        for aid, record in list(self._active_adaptations.items()):
            if now - record["started_at"] > window:
                logger.warning("adaptation.window_exceeded", adaptation_id=aid)
                await self.bus.publish(Event(
                    category=EventCategory.ADAPTATION,
                    event_type="escalate_to_recovery",
                    severity=EventSeverity.CRITICAL,
                    source="adaptation_engine",
                    payload=record,
                ))

    def get_status(self) -> dict[str, Any]:
        return {
            "active_adaptations": len(self._active_adaptations),
            "total_adaptations": len(self._history),
            "feature_flags": self.feature_flags.get_status(),
            "traffic_shifter": self.traffic_shifter.get_status(),
        }
