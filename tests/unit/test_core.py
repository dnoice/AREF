"""
Tests for AREF core components: config, events, metrics, models.
"""

import asyncio
import time

import pytest

from aref.core.config import (
    AREFConfig, CRS_WEIGHT_PROFILES, RiskProfile,
    get_config, reset_config,
)
from aref.core.events import (
    Event, EventBus, EventCategory, EventSeverity,
    get_event_bus, reset_event_bus,
)
from aref.core.metrics import MetricsEngine, IncidentTiming
from aref.core.models import (
    Incident, IncidentSeverity, IncidentStatus, RecoveryTier,
    MaturityLevel, ActionItem, AnomalyClass,
)


class TestConfig:
    def setup_method(self):
        reset_config()

    def test_default_config(self):
        config = get_config()
        assert config.environment == "development"
        assert config.risk_profile == RiskProfile.BALANCED
        assert config.detection.mttd_target_seconds == 300.0
        assert config.absorption.blast_radius_target_pct == 95.0
        assert config.adaptation.latency_target_seconds == 30.0
        assert config.recovery.mttr_target_seconds == 900.0
        assert config.evolution.improvement_velocity_target == 8

    def test_crs_weights_sum_to_one(self):
        for profile, weights in CRS_WEIGHT_PROFILES.items():
            total = sum(weights.values())
            assert abs(total - 1.0) < 0.001, f"{profile}: weights sum to {total}"

    def test_crs_weights_property(self):
        config = get_config()
        weights = config.crs_weights
        assert "detection" in weights
        assert "absorption" in weights
        assert "adaptation" in weights
        assert "recovery" in weights
        assert "evolution" in weights


class TestEventBus:
    def setup_method(self):
        reset_event_bus()

    @pytest.mark.asyncio
    async def test_publish_subscribe(self):
        bus = get_event_bus()
        received = []

        async def handler(event: Event):
            received.append(event)

        bus.subscribe("detection.alert_fired", handler)

        event = Event(
            category=EventCategory.DETECTION,
            event_type="alert_fired",
            severity=EventSeverity.WARNING,
        )
        await bus.publish(event)

        assert len(received) == 1
        assert received[0].event_type == "alert_fired"

    @pytest.mark.asyncio
    async def test_wildcard_subscription(self):
        bus = get_event_bus()
        received = []

        async def handler(event: Event):
            received.append(event)

        bus.subscribe("detection.*", handler)

        await bus.publish(Event(category=EventCategory.DETECTION, event_type="alert_fired"))
        await bus.publish(Event(category=EventCategory.DETECTION, event_type="anomaly_detected"))
        await bus.publish(Event(category=EventCategory.RECOVERY, event_type="recovery_started"))

        assert len(received) == 2  # Only detection events

    @pytest.mark.asyncio
    async def test_event_history(self):
        bus = get_event_bus()

        for i in range(5):
            await bus.publish(Event(
                category=EventCategory.SYSTEM,
                event_type=f"test_{i}",
            ))

        history = bus.get_history(limit=3)
        assert len(history) == 3

    @pytest.mark.asyncio
    async def test_timeline_by_correlation(self):
        bus = get_event_bus()
        cid = "test-correlation-123"

        for i in range(3):
            await bus.publish(Event(
                category=EventCategory.DETECTION,
                event_type=f"step_{i}",
                correlation_id=cid,
            ))
        await bus.publish(Event(
            category=EventCategory.DETECTION,
            event_type="unrelated",
            correlation_id="other",
        ))

        timeline = bus.get_timeline(cid)
        assert len(timeline) == 3


class TestMetricsEngine:
    def test_compute_mttd(self):
        engine = MetricsEngine()
        engine.record_incident(IncidentTiming(onset=100.0, detected=130.0))
        engine.record_incident(IncidentTiming(onset=200.0, detected=250.0))

        mttd = engine.compute_mttd()
        assert mttd == 40.0  # (30 + 50) / 2

    def test_compute_mttr(self):
        engine = MetricsEngine()
        engine.record_incident(IncidentTiming(onset=100.0, detected=130.0, recovered=200.0))
        engine.record_incident(IncidentTiming(onset=300.0, detected=320.0, recovered=500.0))

        mttr = engine.compute_mttr()
        assert mttr == 150.0  # (100 + 200) / 2

    def test_compute_availability(self):
        engine = MetricsEngine()
        engine.record_incident(IncidentTiming(onset=0, detected=10, recovered=100))
        engine.record_uptime(3600)

        avail = engine.compute_availability()
        assert avail is not None
        assert avail > 95.0

    def test_compute_error_budget(self):
        # SLO 99.9% over 30 days, 1 hour downtime
        eb = MetricsEngine.compute_error_budget(
            slo=0.999,
            downtime=3600,
            window=2592000,
        )
        # Budget = 0.001 - (3600/2592000) = 0.001 - 0.00139 = negative
        assert eb < 0  # Budget exhausted

    def test_compute_crs(self):
        scores = {
            "detection": 3.0, "absorption": 3.0, "adaptation": 3.0,
            "recovery": 3.0, "evolution": 3.0,
        }
        crs = MetricsEngine.compute_crs(scores, RiskProfile.BALANCED)
        assert crs == 3.0  # Balanced weights, all 3.0 = 3.0

        crs_avail = MetricsEngine.compute_crs(scores, RiskProfile.AVAILABILITY_CRITICAL)
        assert crs_avail == 3.0  # Same scores, different weights but same result


class TestModels:
    def test_incident_lifecycle(self):
        incident = Incident(
            severity=IncidentSeverity.SEV2,
            title="Test incident",
            source_service="orders",
        )
        assert incident.status == IncidentStatus.DETECTED
        assert incident.incident_id.startswith("INC-")
        assert incident.time_to_detect is None

        incident.detected_time = incident.onset_time + 30
        assert incident.time_to_detect == pytest.approx(30.0)

        incident.resolved_time = incident.onset_time + 600
        assert incident.time_to_recover == pytest.approx(600.0)

    def test_incident_timeline(self):
        incident = Incident(title="Test")
        incident.add_timeline_entry("detected", "Alert fired")
        incident.add_timeline_entry("absorbed", "Circuit breaker opened")

        assert len(incident.timeline) == 2
        assert incident.timeline[0]["action"] == "detected"

    def test_action_item_overdue(self):
        item = ActionItem(
            title="Fix detection",
            due_date=time.time() - 3600,  # 1 hour ago
        )
        assert item.is_overdue

        item2 = ActionItem(
            title="Fix detection",
            due_date=time.time() + 3600,  # 1 hour from now
        )
        assert not item2.is_overdue

    def test_maturity_levels(self):
        assert MaturityLevel.REACTIVE == 1
        assert MaturityLevel.OPTIMIZING == 5

    def test_recovery_tiers(self):
        assert RecoveryTier.T0_EMERGENCY == 0
        assert RecoveryTier.T4_HARDENING == 4
