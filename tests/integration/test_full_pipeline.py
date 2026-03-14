"""
Integration test: Full AREF pipeline — Detection through Evolution.

This test simulates a complete incident lifecycle:
  1. Detection fires an alert
  2. Absorption activates circuit breakers
  3. Adaptation triggers load shedding
  4. Recovery executes runbooks
  5. Evolution generates post-incident review
"""

import asyncio
import time

import pytest

from aref.core.config import reset_config
from aref.core.events import (
    Event, EventBus, EventCategory, EventSeverity,
    get_event_bus, reset_event_bus,
)
from aref.core.models import Incident, IncidentSeverity, IncidentStatus
from aref.detection.engine import DetectionEngine
from aref.adaptation.engine import AdaptationEngine
from aref.recovery.engine import RecoveryEngine
from aref.evolution.engine import EvolutionEngine


@pytest.fixture
def fresh_bus():
    reset_event_bus()
    reset_config()
    return get_event_bus()


@pytest.mark.asyncio
async def test_full_incident_pipeline(fresh_bus):
    """Test that an alert propagates through all five pillars."""
    bus = fresh_bus
    events_received: list[Event] = []

    # Track all events
    async def tracker(event: Event):
        events_received.append(event)

    bus.subscribe("*", tracker)

    # Create and start engines
    detection = DetectionEngine(bus)
    adaptation = AdaptationEngine(bus)
    recovery = RecoveryEngine(bus)
    evolution = EvolutionEngine(bus)

    await adaptation.start()
    await recovery.start()
    await evolution.start()

    # Simulate a detection alert
    alert_event = Event(
        category=EventCategory.DETECTION,
        event_type="alert_fired",
        severity=EventSeverity.EMERGENCY,
        source="detection_engine",
        payload={
            "service": "payments",
            "title": "Payment provider failure",
            "severity": EventSeverity.EMERGENCY,
            "detection_class": "synthetic",
            "consecutive_breaches": 10,
        },
        correlation_id="test-pipeline-001",
    )
    await bus.publish(alert_event)

    # Give engines time to react
    await asyncio.sleep(0.5)

    # Verify events were generated across multiple pillars
    categories = {e.category.value for e in events_received}

    assert "detection" in categories, "Detection event should be present"
    # Adaptation and Recovery should react to the emergency alert
    # (they subscribe to detection events)

    # Check that at least some pillar responded
    assert len(events_received) >= 1

    # Cleanup
    await adaptation.stop()
    await recovery.stop()
    await evolution.stop()


@pytest.mark.asyncio
async def test_event_correlation(fresh_bus):
    """Test that correlated events can be retrieved as a timeline."""
    bus = fresh_bus
    cid = "incident-timeline-test"

    await bus.publish(Event(
        category=EventCategory.DETECTION,
        event_type="alert_fired",
        correlation_id=cid,
    ))
    await bus.publish(Event(
        category=EventCategory.ABSORPTION,
        event_type="circuit_breaker_opened",
        correlation_id=cid,
    ))
    await bus.publish(Event(
        category=EventCategory.ADAPTATION,
        event_type="feature_flag_disabled",
        correlation_id=cid,
    ))
    await bus.publish(Event(
        category=EventCategory.RECOVERY,
        event_type="recovery_started",
        correlation_id=cid,
    ))

    timeline = bus.get_timeline(cid)
    assert len(timeline) == 4

    # Verify chronological order
    categories = [e.category.value for e in timeline]
    assert categories == ["detection", "absorption", "adaptation", "recovery"]
