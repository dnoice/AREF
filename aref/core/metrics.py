"""
AREF Metrics Collector — Central metrics registry using Prometheus client.

Exposes all key AREF formulas from blueprint Section 6:
  - MTTD (Mean Time to Detect)
  - MTTR (Mean Time to Recover)
  - Availability (MTBF-based)
  - Error Budget Remaining
  - Composite Resilience Score (CRS)

Each pillar registers its own domain-specific metrics through this collector.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from prometheus_client import Counter, Gauge, Histogram, Summary

from aref.core.config import CRS_WEIGHT_PROFILES, RiskProfile, get_config


# ---------------------------------------------------------------------------
# Prometheus metrics — global registry
# ---------------------------------------------------------------------------

# Detection
INCIDENTS_DETECTED = Counter(
    "aref_incidents_detected_total", "Total incidents detected", ["detection_class"]
)
MTTD_HISTOGRAM = Histogram(
    "aref_mttd_seconds", "Mean Time to Detect distribution",
    buckets=[5, 15, 30, 60, 120, 300, 600],
)
ALERT_FIRED = Counter("aref_alerts_fired_total", "Alerts fired", ["severity", "service"])
ALERT_ACTIONED = Counter("aref_alerts_actioned_total", "Alerts that led to action", ["service"])

# Absorption
CIRCUIT_BREAKER_STATE = Gauge(
    "aref_circuit_breaker_state", "Circuit breaker state (0=closed, 1=half-open, 2=open)",
    ["service", "dependency"],
)
BLAST_RADIUS_CONTAINED = Gauge(
    "aref_blast_radius_contained_pct", "Blast radius containment percentage", ["incident_id"]
)
RATE_LIMIT_REJECTED = Counter(
    "aref_rate_limit_rejected_total", "Requests rejected by rate limiter", ["service"]
)

# Adaptation
ADAPTATION_LATENCY = Histogram(
    "aref_adaptation_latency_seconds", "Time from detection to adaptation",
    buckets=[1, 5, 10, 30, 60, 120],
)
SCALING_EVENTS = Counter("aref_scaling_events_total", "Auto-scaling events", ["direction"])
FEATURE_FLAGS_TOGGLED = Counter(
    "aref_feature_flags_toggled_total", "Feature flags toggled", ["flag", "action"]
)
TRAFFIC_SHIFTED = Counter(
    "aref_traffic_shifted_total", "Traffic shift events", ["from_region", "to_region"]
)

# Recovery
MTTR_HISTOGRAM = Histogram(
    "aref_mttr_seconds", "Mean Time to Recover distribution",
    buckets=[60, 300, 600, 900, 1800, 3600],
)
RECOVERY_TIER_ACTIVE = Gauge(
    "aref_recovery_tier_active", "Currently active recovery tier", ["incident_id"]
)
RUNBOOK_EXECUTIONS = Counter(
    "aref_runbook_executions_total", "Runbook executions", ["runbook", "outcome"]
)

# Evolution
POST_INCIDENT_REVIEWS = Counter("aref_post_incident_reviews_total", "Post-incident reviews completed")
ACTION_ITEMS_CREATED = Counter("aref_action_items_created_total", "Action items created")
ACTION_ITEMS_COMPLETED = Counter("aref_action_items_completed_total", "Action items completed on time")
RECURRENCE_DETECTED = Counter("aref_recurrence_detected_total", "Recurring incident patterns found")

# Maturity
CRS_SCORE = Gauge("aref_crs_score", "Composite Resilience Score", ["risk_profile"])
PILLAR_MATURITY = Gauge("aref_pillar_maturity", "Pillar maturity level (1-5)", ["pillar"])

# System health
SERVICE_UP = Gauge("aref_service_up", "Service health (1=up, 0=down)", ["service"])
REQUEST_LATENCY = Histogram(
    "aref_request_latency_seconds", "Request latency", ["service", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)
ERROR_RATE = Gauge("aref_error_rate", "Current error rate", ["service"])


# ---------------------------------------------------------------------------
# AREF Formula Engine
# ---------------------------------------------------------------------------

@dataclass
class IncidentTiming:
    onset: float
    detected: float | None = None
    recovered: float | None = None

    @property
    def time_to_detect(self) -> float | None:
        if self.detected is None:
            return None
        return self.detected - self.onset

    @property
    def time_to_recover(self) -> float | None:
        if self.recovered is None:
            return None
        return self.recovered - self.onset


class MetricsEngine:
    """Computes AREF key formulas from collected incident data."""

    def __init__(self) -> None:
        self._incidents: deque[IncidentTiming] = deque(maxlen=1000)
        self._uptime_intervals: deque[float] = deque(maxlen=1000)
        self._downtime_intervals: deque[float] = deque(maxlen=1000)

    def record_incident(self, timing: IncidentTiming) -> None:
        self._incidents.append(timing)
        if timing.time_to_detect is not None:
            MTTD_HISTOGRAM.observe(timing.time_to_detect)
        if timing.time_to_recover is not None:
            MTTR_HISTOGRAM.observe(timing.time_to_recover)

    def record_uptime(self, seconds: float) -> None:
        self._uptime_intervals.append(seconds)

    def record_downtime(self, seconds: float) -> None:
        self._downtime_intervals.append(seconds)

    def compute_mttd(self) -> float | None:
        """MTTD = SUM(t_detect - t_onset) / n  [Blueprint 6.2]"""
        detect_times = [i.time_to_detect for i in self._incidents if i.time_to_detect is not None]
        if not detect_times:
            return None
        return sum(detect_times) / len(detect_times)

    def compute_mttr(self) -> float | None:
        """MTTR = SUM(t_recover - t_onset) / n"""
        recover_times = [i.time_to_recover for i in self._incidents if i.time_to_recover is not None]
        if not recover_times:
            return None
        return sum(recover_times) / len(recover_times)

    def compute_mtbf(self) -> float | None:
        """Mean Time Between Failures."""
        if not self._uptime_intervals:
            return None
        return sum(self._uptime_intervals) / len(self._uptime_intervals)

    def compute_availability(self) -> float | None:
        """A = MTBF / (MTBF + MTTR) * 100%  [Blueprint 6.2]"""
        mtbf = self.compute_mtbf()
        mttr = self.compute_mttr()
        if mtbf is None or mttr is None or (mtbf + mttr) == 0:
            return None
        return (mtbf / (mtbf + mttr)) * 100.0

    @staticmethod
    def compute_error_budget(slo: float, downtime: float, window: float) -> float:
        """EB_remaining = (1 - SLO) - (t_downtime / t_window)  [Blueprint 6.2]"""
        if window == 0:
            return 0.0
        return (1.0 - slo) - (downtime / window)

    @staticmethod
    def compute_crs(
        pillar_scores: dict[str, float],
        risk_profile: RiskProfile = RiskProfile.BALANCED,
    ) -> float:
        """CRS = SUM(w_i * M_i), i=1..5  [Blueprint 6.1]"""
        weights = CRS_WEIGHT_PROFILES[risk_profile]
        score = 0.0
        for pillar, weight in weights.items():
            score += weight * pillar_scores.get(pillar, 1.0)
        return round(score, 3)

    def get_summary(self) -> dict[str, Any]:
        return {
            "mttd": self.compute_mttd(),
            "mttr": self.compute_mttr(),
            "mtbf": self.compute_mtbf(),
            "availability": self.compute_availability(),
            "total_incidents": len(self._incidents),
        }


# Singleton
_engine: MetricsEngine | None = None


def get_metrics_engine() -> MetricsEngine:
    global _engine
    if _engine is None:
        _engine = MetricsEngine()
    return _engine
