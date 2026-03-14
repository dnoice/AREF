"""
Adaptation Decision Tree — Blueprint Section 3.3.2.

Decision flow:
  1. Classify the anomaly: transient, persistent, or escalating?
  2. Assess blast radius: which components and users are affected?
  3. Evaluate available strategies against current system state
  4. Select the minimum-impact strategy that addresses the anomaly
  5. Execute with automated rollback triggers in place
  6. If ineffective within the adaptation window, escalate to Recovery
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

from aref.core.events import EventSeverity
from aref.core.models import AnomalyClass

logger = structlog.get_logger(__name__)


@dataclass
class AdaptationAction:
    strategy: str
    service: str
    parameters: dict[str, Any] = field(default_factory=dict)
    rollback_strategy: str = ""
    risk_level: str = "low"  # low, medium, high


# Strategy -> rollback risk mapping from blueprint table
STRATEGY_RISK = {
    "horizontal_scaling": "low",
    "traffic_shifting": "medium",
    "feature_flagging": "low",
    "schema_fallback": "high",
    "dependency_substitution": "medium",
    "cognitive_load_shedding": "low",
}


class AdaptationDecisionTree:
    """
    Implements the six-step decision process from the blueprint.
    Selects the minimum-impact strategy based on anomaly classification and severity.
    """

    def decide(
        self,
        anomaly_class: AnomalyClass,
        severity: EventSeverity,
        service: str,
        context: dict[str, Any] | None = None,
    ) -> AdaptationAction | None:
        ctx = context or {}

        # Step 1: Already classified (anomaly_class parameter)
        # Step 2: Blast radius assessment is done by caller
        # Step 3-4: Select minimum-impact strategy

        if anomaly_class == AnomalyClass.TRANSIENT:
            return self._handle_transient(severity, service, ctx)
        elif anomaly_class == AnomalyClass.PERSISTENT:
            return self._handle_persistent(severity, service, ctx)
        elif anomaly_class == AnomalyClass.ESCALATING:
            return self._handle_escalating(severity, service, ctx)

        return None

    def _handle_transient(
        self, severity: EventSeverity, service: str, ctx: dict[str, Any]
    ) -> AdaptationAction | None:
        """Transient anomalies — prefer low-risk, minimal actions."""
        if severity == EventSeverity.WARNING:
            # Just scale slightly to handle the blip
            return AdaptationAction(
                strategy="horizontal_scaling",
                service=service,
                parameters={"direction": "up", "count": 1},
                rollback_strategy="scale_down",
                risk_level="low",
            )
        elif severity in (EventSeverity.CRITICAL, EventSeverity.EMERGENCY):
            # Feature flag non-essential load
            return AdaptationAction(
                strategy="feature_flagging",
                service=service,
                parameters={"flags": [f"{service}.non_essential"]},
                rollback_strategy="re_enable_flags",
                risk_level="low",
            )
        return None

    def _handle_persistent(
        self, severity: EventSeverity, service: str, ctx: dict[str, Any]
    ) -> AdaptationAction | None:
        """Persistent anomalies — more aggressive action needed."""
        if severity == EventSeverity.WARNING:
            return AdaptationAction(
                strategy="traffic_shifting",
                service=service,
                parameters={"from": service, "to": f"{service}-backup", "weight": 50},
                rollback_strategy="revert_traffic",
                risk_level="medium",
            )
        elif severity == EventSeverity.CRITICAL:
            return AdaptationAction(
                strategy="dependency_substitution",
                service=service,
                parameters={"failed_dependency": ctx.get("dependency", service)},
                rollback_strategy="revert_provider",
                risk_level="medium",
            )
        elif severity == EventSeverity.EMERGENCY:
            # Shed cognitive load + full traffic shift
            return AdaptationAction(
                strategy="cognitive_load_shedding",
                service=service,
                parameters={"reduce_dashboards": True, "mute_non_critical": True},
                rollback_strategy="restore_dashboards",
                risk_level="low",
            )
        return None

    def _handle_escalating(
        self, severity: EventSeverity, service: str, ctx: dict[str, Any]
    ) -> AdaptationAction | None:
        """Escalating anomalies — maximum protective action, prepare for recovery."""
        return AdaptationAction(
            strategy="feature_flagging",
            service=service,
            parameters={
                "flags": [f"{service}.non_essential", f"{service}.experimental"],
                "shed_all_non_critical": True,
            },
            rollback_strategy="re_enable_flags",
            risk_level="low",
        )
