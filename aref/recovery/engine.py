"""
Recovery Engine — Orchestrates tiered recovery from T0 through T4.

The engine progresses through recovery tiers automatically:
  T0 fires immediately and autonomously (no human approval needed)
  T1 begins if T0 doesn't resolve within target window
  T2+ involves human coordination via incident commander

Blueprint critical requirement: "Every team must execute T0 and T1
without external dependencies or approvals."
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import structlog

from aref.core.config import get_config
from aref.core.events import Event, EventBus, EventCategory, EventSeverity, get_event_bus
from aref.core.metrics import MTTR_HISTOGRAM, RECOVERY_TIER_ACTIVE, RUNBOOK_EXECUTIONS
from aref.core.models import Incident, IncidentStatus, RecoveryTier
from aref.recovery.runbooks import RunbookExecutor

logger = structlog.get_logger(__name__)


class RecoveryEngine:
    """
    Manages the recovery lifecycle for incidents.
    Automatically escalates through tiers based on time windows.
    """

    def __init__(self, bus: EventBus | None = None) -> None:
        self.config = get_config().recovery
        self.bus = bus or get_event_bus()
        self.runbook_executor = RunbookExecutor()

        self._active_recoveries: dict[str, dict[str, Any]] = {}
        self._history: list[dict[str, Any]] = []
        self._running = False

    async def start(self) -> None:
        self._running = True
        self.bus.subscribe("adaptation.escalate_to_recovery", self._on_escalation)
        self.bus.subscribe("detection.alert_fired", self._on_critical_alert)
        logger.info("recovery.engine.started")

    async def stop(self) -> None:
        self._running = False
        logger.info("recovery.engine.stopped")

    async def _on_critical_alert(self, event: Event) -> None:
        """Auto-trigger T0 recovery on emergency-severity alerts."""
        if event.severity == EventSeverity.EMERGENCY:
            incident = Incident(
                severity=self._map_severity(event.severity),
                title=event.payload.get("title", "Emergency alert"),
                source_service=event.payload.get("service", "unknown"),
                correlation_id=event.correlation_id or event.event_id,
            )
            await self.begin_recovery(incident)

    async def _on_escalation(self, event: Event) -> None:
        """Handle escalation from Adaptation pillar."""
        incident = Incident(
            title=f"Escalated from adaptation: {event.payload.get('strategy', 'unknown')}",
            source_service=event.payload.get("service", "unknown"),
            correlation_id=event.correlation_id or event.event_id,
        )
        await self.begin_recovery(incident)

    async def begin_recovery(self, incident: Incident) -> None:
        """Start the recovery process for an incident, beginning at T0."""
        incident.status = IncidentStatus.RECOVERING
        incident.recovery_start_time = time.time()
        incident.recovery_tier = RecoveryTier.T0_EMERGENCY

        recovery_id = incident.incident_id
        self._active_recoveries[recovery_id] = {
            "incident": incident,
            "started_at": time.time(),
            "current_tier": RecoveryTier.T0_EMERGENCY,
            "tier_history": [],
        }

        RECOVERY_TIER_ACTIVE.labels(incident_id=recovery_id).set(0)
        incident.add_timeline_entry("recovery_started", "T0 Emergency Stabilization initiated")

        await self.bus.publish(Event(
            category=EventCategory.RECOVERY,
            event_type="recovery_started",
            severity=EventSeverity.CRITICAL,
            source="recovery_engine",
            payload={"incident_id": recovery_id, "tier": "T0"},
            correlation_id=incident.correlation_id,
        ))

        logger.info("recovery.started", incident_id=recovery_id, tier="T0")

        # Execute T0 automatically
        await self._execute_tier(recovery_id, RecoveryTier.T0_EMERGENCY)

    async def _execute_tier(self, recovery_id: str, tier: RecoveryTier) -> None:
        """Execute recovery actions for a specific tier."""
        recovery = self._active_recoveries.get(recovery_id)
        if not recovery:
            return

        incident: Incident = recovery["incident"]
        recovery["current_tier"] = tier
        recovery["tier_history"].append({
            "tier": tier.name,
            "started_at": time.time(),
        })
        RECOVERY_TIER_ACTIVE.labels(incident_id=recovery_id).set(tier.value)

        tier_name = {
            RecoveryTier.T0_EMERGENCY: "Emergency Stabilization",
            RecoveryTier.T1_MINIMUM: "Minimum Viable Recovery",
            RecoveryTier.T2_FUNCTIONAL: "Functional Recovery",
            RecoveryTier.T3_FULL: "Full Restoration",
            RecoveryTier.T4_HARDENING: "Post-Incident Hardening",
        }.get(tier, "Unknown")

        incident.add_timeline_entry(f"tier_{tier.name.lower()}", f"{tier_name} initiated")

        # Execute runbooks for this tier
        runbooks = self.runbook_executor.get_runbooks_for_tier(tier)
        for runbook in runbooks:
            try:
                result = await self.runbook_executor.execute(runbook, incident)
                RUNBOOK_EXECUTIONS.labels(runbook=runbook.name, outcome="success").inc()
                incident.add_timeline_entry(
                    f"runbook_{runbook.name}",
                    f"Executed: {result.get('summary', 'completed')}",
                )
            except Exception as e:
                RUNBOOK_EXECUTIONS.labels(runbook=runbook.name, outcome="failure").inc()
                incident.add_timeline_entry(
                    f"runbook_{runbook.name}_failed",
                    f"Failed: {str(e)}",
                )

        await self.bus.publish(Event(
            category=EventCategory.RECOVERY,
            event_type=f"tier_{tier.name.lower()}_completed",
            source="recovery_engine",
            payload={"incident_id": recovery_id, "tier": tier.name},
            correlation_id=incident.correlation_id,
        ))

    async def escalate_tier(self, recovery_id: str) -> RecoveryTier | None:
        """Escalate to the next recovery tier."""
        recovery = self._active_recoveries.get(recovery_id)
        if not recovery:
            return None

        current = recovery["current_tier"]
        if current.value >= RecoveryTier.T4_HARDENING.value:
            return None

        next_tier = RecoveryTier(current.value + 1)
        await self._execute_tier(recovery_id, next_tier)
        return next_tier

    async def resolve_recovery(self, recovery_id: str) -> None:
        """Mark a recovery as resolved."""
        recovery = self._active_recoveries.pop(recovery_id, None)
        if not recovery:
            return

        incident: Incident = recovery["incident"]
        incident.status = IncidentStatus.RESOLVED
        incident.resolved_time = time.time()
        incident.add_timeline_entry("recovery_resolved", "Incident resolved")

        if incident.time_to_recover:
            MTTR_HISTOGRAM.observe(incident.time_to_recover)

        self._history.append({
            "incident_id": recovery_id,
            "duration": incident.time_to_recover,
            "tiers_used": [t["tier"] for t in recovery["tier_history"]],
            "resolved_at": time.time(),
        })

        await self.bus.publish(Event(
            category=EventCategory.RECOVERY,
            event_type="recovery_resolved",
            source="recovery_engine",
            payload=incident.to_dict(),
            correlation_id=incident.correlation_id,
        ))

        logger.info("recovery.resolved", incident_id=recovery_id, duration=incident.time_to_recover)

    def _map_severity(self, event_sev: EventSeverity) -> Any:
        from aref.core.models import IncidentSeverity
        mapping = {
            EventSeverity.EMERGENCY: IncidentSeverity.SEV1,
            EventSeverity.CRITICAL: IncidentSeverity.SEV1,
            EventSeverity.WARNING: IncidentSeverity.SEV2,
            EventSeverity.INFO: IncidentSeverity.SEV3,
        }
        return mapping.get(event_sev, IncidentSeverity.SEV3)

    def get_active_recoveries(self) -> list[dict[str, Any]]:
        return [
            {
                "incident_id": rid,
                "current_tier": r["current_tier"].name,
                "started_at": r["started_at"],
                "elapsed": time.time() - r["started_at"],
            }
            for rid, r in self._active_recoveries.items()
        ]

    def get_status(self) -> dict[str, Any]:
        return {
            "active_recoveries": len(self._active_recoveries),
            "total_recovered": len(self._history),
            "recoveries": self.get_active_recoveries(),
        }
