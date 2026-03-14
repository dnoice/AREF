"""
Evolution Engine — Orchestrates the post-incident learning cycle.

Listens for recovery.resolved events and automatically:
  1. Generates post-incident reviews
  2. Extracts action items
  3. Matches patterns against the knowledge base
  4. Tracks improvement velocity
"""

from __future__ import annotations

import time
from typing import Any

import structlog

from aref.core.config import get_config
from aref.core.events import Event, EventBus, EventCategory, EventSeverity, get_event_bus
from aref.core.metrics import (
    ACTION_ITEMS_COMPLETED, ACTION_ITEMS_CREATED, POST_INCIDENT_REVIEWS, RECURRENCE_DETECTED,
)
from aref.core.models import ActionItem, Incident

from aref.evolution.post_incident import PostIncidentReviewGenerator
from aref.evolution.tracker import ActionTracker
from aref.evolution.patterns import PatternMatcher
from aref.evolution.knowledge_base import KnowledgeBase

logger = structlog.get_logger(__name__)


class EvolutionEngine:
    """
    Central evolution orchestrator.
    Converts incidents into structured learning and tracked improvements.
    """

    def __init__(self, bus: EventBus | None = None) -> None:
        self.config = get_config().evolution
        self.bus = bus or get_event_bus()

        self.review_generator = PostIncidentReviewGenerator()
        self.action_tracker = ActionTracker()
        self.pattern_matcher = PatternMatcher()
        self.knowledge_base = KnowledgeBase()

        self._reviews: list[dict[str, Any]] = []
        self._running = False

    async def start(self) -> None:
        self._running = True
        self.bus.subscribe("recovery.recovery_resolved", self._on_recovery_resolved)
        logger.info("evolution.engine.started")

    async def stop(self) -> None:
        self._running = False

    async def _on_recovery_resolved(self, event: Event) -> None:
        """Automatically generate post-incident review when recovery completes."""
        incident_data = event.payload
        correlation_id = event.correlation_id or ""

        # Get full event timeline for this incident
        timeline = self.bus.get_timeline(correlation_id)

        review = self.review_generator.generate(incident_data, timeline)
        self._reviews.append(review)
        POST_INCIDENT_REVIEWS.inc()

        # Generate action items from the review
        actions = self._extract_actions(review, incident_data)
        for action in actions:
            self.action_tracker.add(action)
            ACTION_ITEMS_CREATED.inc()

        # Pattern matching
        matches = self.pattern_matcher.find_matches(incident_data)
        if matches:
            RECURRENCE_DETECTED.inc()
            review["recurrence_matches"] = matches

        # Store in knowledge base
        self.knowledge_base.store_incident(incident_data, review)

        await self.bus.publish(Event(
            category=EventCategory.EVOLUTION,
            event_type="review_completed",
            source="evolution_engine",
            payload={
                "incident_id": incident_data.get("incident_id", ""),
                "review_summary": review.get("summary", ""),
                "action_items": len(actions),
                "recurrence_detected": len(matches) > 0,
            },
            correlation_id=correlation_id,
        ))

        logger.info(
            "evolution.review_generated",
            incident_id=incident_data.get("incident_id", ""),
            actions=len(actions),
            recurrences=len(matches),
        )

    def _extract_actions(self, review: dict[str, Any], incident_data: dict[str, Any]) -> list[ActionItem]:
        """Generate action items from a post-incident review."""
        actions = []
        incident_id = incident_data.get("incident_id", "")

        # Standard action items based on review findings
        if review.get("detection_effectiveness", 0) < 0.8:
            actions.append(ActionItem(
                incident_id=incident_id,
                title="Improve detection coverage",
                description=f"MTTD was {review.get('mttd', 'N/A')}s. Review alert thresholds and add anomaly detection.",
                priority="high",
                pillar="detection",
            ))

        if review.get("blast_radius_containment", 0) < 95:
            actions.append(ActionItem(
                incident_id=incident_id,
                title="Improve blast radius containment",
                description="Add or verify circuit breakers and bulkheads on affected dependency paths.",
                priority="high",
                pillar="absorption",
            ))

        if review.get("adaptation_latency", 0) > 30:
            actions.append(ActionItem(
                incident_id=incident_id,
                title="Reduce adaptation latency",
                description="Automate adaptation triggers that are currently manual.",
                priority="medium",
                pillar="adaptation",
            ))

        if review.get("recovery_duration", 0) > 900:  # > 15 min
            actions.append(ActionItem(
                incident_id=incident_id,
                title="Improve recovery time",
                description="Review and automate T0/T1 runbooks for faster stabilization.",
                priority="high",
                pillar="recovery",
            ))

        # Always add a "document learnings" action
        actions.append(ActionItem(
            incident_id=incident_id,
            title="Document incident learnings",
            description="Share incident review with the broader organization within 72 hours.",
            priority="medium",
            pillar="evolution",
            due_date=time.time() + (72 * 3600),  # 72-hour deadline per blueprint
        ))

        return actions

    def get_improvement_velocity(self) -> dict[str, Any]:
        """Compute improvement velocity — target > 8 actions/quarter per blueprint."""
        stats = self.action_tracker.get_stats()
        return {
            "actions_completed_this_quarter": stats.get("completed_this_quarter", 0),
            "target": self.config.improvement_velocity_target,
            "on_track": stats.get("completed_this_quarter", 0) >= self.config.improvement_velocity_target,
            "completion_rate": stats.get("completion_rate", 0),
            "target_completion_rate": self.config.action_completion_rate_target,
        }

    def get_status(self) -> dict[str, Any]:
        return {
            "total_reviews": len(self._reviews),
            "action_tracker": self.action_tracker.get_stats(),
            "knowledge_base_size": self.knowledge_base.size,
            "improvement_velocity": self.get_improvement_velocity(),
        }
