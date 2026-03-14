"""
Runbook System — Blueprint Section 3.4.2.

Executable, version-controlled runbooks defined in YAML.
Standards:
  - Every step is a concrete, executable action
  - Runbooks exercised quarterly through drills
  - Role-specific: each step identifies who executes it
  - Time-bounded with escalation triggers
  - External dependencies explicitly documented
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
import structlog

from aref.core.models import Incident, RecoveryTier

logger = structlog.get_logger(__name__)


@dataclass
class RunbookStep:
    order: int
    action: str
    description: str
    role: str = "engineer"        # Who executes this step
    timeout_seconds: float = 60.0
    escalation: str = ""          # What to do if step fails
    automated: bool = False
    external_dependency: str = ""  # Explicitly documented per blueprint


@dataclass
class Runbook:
    name: str
    service: str
    recovery_tier: RecoveryTier
    description: str = ""
    steps: list[RunbookStep] = field(default_factory=list)
    version: str = "1.0.0"
    last_drilled: float | None = None
    external_dependencies: list[str] = field(default_factory=list)


class RunbookExecutor:
    """Loads and executes runbooks for recovery operations."""

    def __init__(self) -> None:
        self._runbooks: list[Runbook] = []
        self._execution_history: list[dict[str, Any]] = []
        self._load_defaults()

    def _load_defaults(self) -> None:
        """Load default runbooks that cover the standard recovery tiers."""
        # T0: Emergency Stabilization — fully automated, no approvals
        self._runbooks.append(Runbook(
            name="t0_emergency_stabilization",
            service="*",
            recovery_tier=RecoveryTier.T0_EMERGENCY,
            description="Automated emergency stabilization — stop active bleeding",
            steps=[
                RunbookStep(1, "identify_failing_component", "Identify which component is failing", automated=True, timeout_seconds=15),
                RunbookStep(2, "activate_circuit_breakers", "Open circuit breakers on failing dependencies", automated=True, timeout_seconds=5),
                RunbookStep(3, "enable_degradation", "Switch affected services to degraded mode", automated=True, timeout_seconds=10),
                RunbookStep(4, "shed_non_critical_load", "Disable non-critical features via feature flags", automated=True, timeout_seconds=5),
                RunbookStep(5, "notify_on_call", "Page on-call engineer with incident summary", automated=True, timeout_seconds=10),
            ],
        ))

        # T1: Minimum Viable Recovery — IC-led
        self._runbooks.append(Runbook(
            name="t1_minimum_viable_recovery",
            service="*",
            recovery_tier=RecoveryTier.T1_MINIMUM,
            description="Restore core functions at reduced capacity",
            steps=[
                RunbookStep(1, "assess_blast_radius", "Map affected services and user impact", role="incident_commander", timeout_seconds=120),
                RunbookStep(2, "verify_circuit_breakers", "Confirm circuit breakers are in correct state", role="engineer", automated=True, timeout_seconds=30),
                RunbookStep(3, "scale_healthy_services", "Scale up healthy service instances", role="engineer", automated=True, timeout_seconds=60),
                RunbookStep(4, "redirect_traffic", "Shift traffic away from failing components", role="engineer", timeout_seconds=120),
                RunbookStep(5, "verify_core_flow", "Confirm core business flow is operational", role="engineer", timeout_seconds=60),
                RunbookStep(6, "update_status_page", "Communicate status to stakeholders", role="incident_commander", timeout_seconds=30),
            ],
        ))

        # T2: Functional Recovery
        self._runbooks.append(Runbook(
            name="t2_functional_recovery",
            service="*",
            recovery_tier=RecoveryTier.T2_FUNCTIONAL,
            description="Restore all customer-facing services to operational",
            steps=[
                RunbookStep(1, "diagnose_root_cause", "Identify contributing factors", role="engineer", timeout_seconds=600),
                RunbookStep(2, "apply_fix_or_rollback", "Deploy fix or rollback to last known good", role="engineer", timeout_seconds=300),
                RunbookStep(3, "restore_full_traffic", "Revert traffic shifts, restore normal routing", role="engineer", timeout_seconds=120),
                RunbookStep(4, "re_enable_features", "Restore feature flags to normal state", role="engineer", automated=True, timeout_seconds=30),
                RunbookStep(5, "validate_all_services", "Run full health check suite", role="engineer", automated=True, timeout_seconds=120),
            ],
        ))

    def load_from_yaml(self, path: str | Path) -> None:
        """Load runbooks from a YAML file."""
        path = Path(path)
        if not path.exists():
            return

        with open(path) as f:
            data = yaml.safe_load(f)

        for rb_data in data.get("runbooks", []):
            steps = [
                RunbookStep(
                    order=s.get("order", i + 1),
                    action=s["action"],
                    description=s.get("description", ""),
                    role=s.get("role", "engineer"),
                    timeout_seconds=s.get("timeout_seconds", 60),
                    automated=s.get("automated", False),
                )
                for i, s in enumerate(rb_data.get("steps", []))
            ]

            self._runbooks.append(Runbook(
                name=rb_data["name"],
                service=rb_data.get("service", "*"),
                recovery_tier=RecoveryTier(rb_data.get("tier", 0)),
                description=rb_data.get("description", ""),
                steps=steps,
                version=rb_data.get("version", "1.0.0"),
            ))

    def get_runbooks_for_tier(self, tier: RecoveryTier) -> list[Runbook]:
        return [rb for rb in self._runbooks if rb.recovery_tier == tier]

    async def execute(self, runbook: Runbook, incident: Incident) -> dict[str, Any]:
        """Execute a runbook step by step."""
        start = time.time()
        results = []

        for step in runbook.steps:
            step_start = time.time()
            try:
                # Simulate step execution
                result = await self._execute_step(step, incident)
                results.append({
                    "step": step.order,
                    "action": step.action,
                    "status": "completed",
                    "duration": time.time() - step_start,
                    **result,
                })
            except Exception as e:
                results.append({
                    "step": step.order,
                    "action": step.action,
                    "status": "failed",
                    "error": str(e),
                    "duration": time.time() - step_start,
                })
                if step.escalation:
                    logger.warning("runbook.step_failed.escalating", step=step.action, escalation=step.escalation)
                break

        execution = {
            "runbook": runbook.name,
            "incident_id": incident.incident_id,
            "tier": runbook.recovery_tier.name,
            "steps_completed": len([r for r in results if r["status"] == "completed"]),
            "total_steps": len(runbook.steps),
            "duration": time.time() - start,
            "results": results,
            "summary": f"Completed {len([r for r in results if r['status'] == 'completed'])}/{len(runbook.steps)} steps",
        }
        self._execution_history.append(execution)
        return execution

    async def _execute_step(self, step: RunbookStep, incident: Incident) -> dict[str, Any]:
        """Execute a single runbook step. In production, this dispatches to actual systems."""
        import asyncio
        # Simulate execution time
        await asyncio.sleep(0.1)

        return {
            "action": step.action,
            "role": step.role,
            "automated": step.automated,
        }

    def get_execution_history(self) -> list[dict[str, Any]]:
        return self._execution_history
