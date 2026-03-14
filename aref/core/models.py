"""
AREF Core Data Models — Shared domain objects used across all pillars.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any


# ---------------------------------------------------------------------------
# Incident Models
# ---------------------------------------------------------------------------

class IncidentSeverity(str, Enum):
    SEV1 = "sev1"  # Critical — customer-facing outage
    SEV2 = "sev2"  # Major — degraded service
    SEV3 = "sev3"  # Minor — limited impact
    SEV4 = "sev4"  # Low — cosmetic or edge case


class IncidentStatus(str, Enum):
    DETECTED = "detected"
    ABSORBING = "absorbing"
    ADAPTING = "adapting"
    RECOVERING = "recovering"
    RESOLVED = "resolved"
    POST_REVIEW = "post_review"
    CLOSED = "closed"


class RecoveryTier(IntEnum):
    """Blueprint Section 3.4.1 — Recovery Tiers T0-T4."""
    T0_EMERGENCY = 0     # Emergency stabilization (0-5 min)
    T1_MINIMUM = 1       # Minimum viable recovery (5-15 min)
    T2_FUNCTIONAL = 2    # Functional recovery (15-60 min)
    T3_FULL = 3          # Full restoration (1-4 hours)
    T4_HARDENING = 4     # Post-incident hardening (1-2 weeks)


class AnomalyClass(str, Enum):
    """Blueprint Section 3.3.2 — Anomaly classification."""
    TRANSIENT = "transient"
    PERSISTENT = "persistent"
    ESCALATING = "escalating"


class DetectionClass(str, Enum):
    """Blueprint Section 3.1.1 — Detection taxonomy."""
    THRESHOLD = "threshold"
    ANOMALY = "anomaly"
    SYNTHETIC = "synthetic"
    CHANGE_CORRELATION = "change_correlation"
    HUMAN_OBSERVATION = "human_observation"
    PREDICTIVE = "predictive"


class MaturityLevel(IntEnum):
    """Blueprint Section 4.1 — Maturity levels."""
    REACTIVE = 1
    MANAGED = 2
    DEFINED = 3
    MEASURED = 4
    OPTIMIZING = 5


@dataclass
class ServiceInfo:
    name: str
    host: str
    port: int
    health_endpoint: str = "/health"
    dependencies: list[str] = field(default_factory=list)
    slis: dict[str, float] = field(default_factory=dict)
    slos: dict[str, float] = field(default_factory=dict)
    degradation_tiers: list[str] = field(default_factory=list)


@dataclass
class Incident:
    incident_id: str = field(default_factory=lambda: f"INC-{uuid.uuid4().hex[:8].upper()}")
    severity: IncidentSeverity = IncidentSeverity.SEV3
    status: IncidentStatus = IncidentStatus.DETECTED
    title: str = ""
    description: str = ""
    source_service: str = ""
    affected_services: list[str] = field(default_factory=list)
    detection_class: DetectionClass = DetectionClass.THRESHOLD
    anomaly_class: AnomalyClass = AnomalyClass.TRANSIENT
    recovery_tier: RecoveryTier = RecoveryTier.T0_EMERGENCY
    correlation_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    # Timestamps
    onset_time: float = field(default_factory=time.time)
    detected_time: float | None = None
    absorbed_time: float | None = None
    adapted_time: float | None = None
    recovery_start_time: float | None = None
    resolved_time: float | None = None

    # Collected data
    timeline: list[dict[str, Any]] = field(default_factory=list)
    contributing_factors: list[str] = field(default_factory=list)
    action_items: list[dict[str, Any]] = field(default_factory=list)
    blast_radius: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_timeline_entry(self, action: str, details: str = "", actor: str = "system") -> None:
        self.timeline.append({
            "timestamp": time.time(),
            "action": action,
            "details": details,
            "actor": actor,
        })

    @property
    def time_to_detect(self) -> float | None:
        if self.detected_time is None:
            return None
        return self.detected_time - self.onset_time

    @property
    def time_to_recover(self) -> float | None:
        if self.resolved_time is None:
            return None
        return self.resolved_time - self.onset_time

    @property
    def duration(self) -> float | None:
        if self.resolved_time is None:
            return None
        return self.resolved_time - self.onset_time

    def to_dict(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "severity": self.severity.value,
            "status": self.status.value,
            "title": self.title,
            "description": self.description,
            "source_service": self.source_service,
            "affected_services": self.affected_services,
            "detection_class": self.detection_class.value,
            "anomaly_class": self.anomaly_class.value,
            "recovery_tier": self.recovery_tier.value,
            "correlation_id": self.correlation_id,
            "onset_time": self.onset_time,
            "detected_time": self.detected_time,
            "resolved_time": self.resolved_time,
            "time_to_detect": self.time_to_detect,
            "time_to_recover": self.time_to_recover,
            "timeline_entries": len(self.timeline),
            "contributing_factors": self.contributing_factors,
            "action_items_count": len(self.action_items),
        }


@dataclass
class ActionItem:
    action_id: str = field(default_factory=lambda: f"ACT-{uuid.uuid4().hex[:8].upper()}")
    incident_id: str = ""
    title: str = ""
    description: str = ""
    owner: str = ""
    priority: str = "medium"
    status: str = "open"
    due_date: float | None = None
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    pillar: str = ""

    @property
    def is_overdue(self) -> bool:
        if self.due_date is None or self.status == "completed":
            return False
        return time.time() > self.due_date


@dataclass
class HealthCheck:
    service: str
    status: str = "healthy"
    latency_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def is_healthy(self) -> bool:
        return self.status == "healthy"
