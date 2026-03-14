"""
Post-Incident Review Generator — Blueprint Section 3.5.1.

Generates structured post-incident reviews following the 6-step process:
  1. Timeline Reconstruction
  2. Contributing Factor Analysis
  3. Response Effectiveness
  4. Action Item Generation
  5. Knowledge Dissemination
  6. Systemic Pattern Matching

"A blameless culture is not about pretending no one was involved.
 It is about acknowledging that the system's design made the error possible
 and fixing the system rather than the person."
"""

from __future__ import annotations

import time
from typing import Any

from aref.core.events import Event


class PostIncidentReviewGenerator:
    """Generates comprehensive post-incident reviews from incident data and event timelines."""

    def generate(self, incident_data: dict[str, Any], timeline: list[Event]) -> dict[str, Any]:
        """Generate a full post-incident review."""
        return {
            "generated_at": time.time(),
            "incident_id": incident_data.get("incident_id", ""),
            "severity": incident_data.get("severity", "unknown"),
            "summary": self._generate_summary(incident_data),
            "timeline": self._reconstruct_timeline(timeline),
            "contributing_factors": self._analyze_contributing_factors(incident_data, timeline),
            "response_effectiveness": self._assess_response(incident_data, timeline),
            "detection_effectiveness": self._compute_detection_effectiveness(incident_data),
            "blast_radius_containment": incident_data.get("blast_radius", {}).get("containment_pct", 0),
            "adaptation_latency": self._compute_adaptation_latency(timeline),
            "recovery_duration": incident_data.get("time_to_recover", 0),
            "mttd": incident_data.get("time_to_detect", 0),
            "lessons_learned": self._extract_lessons(incident_data, timeline),
            "blameless_note": "This review follows AREF blameless principles. "
                            "Focus is on system design improvements, not individual fault.",
        }

    def _generate_summary(self, data: dict[str, Any]) -> str:
        service = data.get("source_service", "unknown")
        severity = data.get("severity", "unknown")
        duration = data.get("time_to_recover")
        duration_str = f"{duration:.0f}s" if duration else "ongoing"
        return (
            f"{severity.upper()} incident affecting {service}. "
            f"Duration: {duration_str}. "
            f"Detection class: {data.get('detection_class', 'unknown')}."
        )

    def _reconstruct_timeline(self, events: list[Event]) -> list[dict[str, Any]]:
        return [
            {
                "timestamp": e.timestamp,
                "category": e.category.value,
                "event_type": e.event_type,
                "severity": e.severity.value,
                "source": e.source,
                "summary": e.payload.get("title", e.event_type),
            }
            for e in sorted(events, key=lambda e: e.timestamp)
        ]

    def _analyze_contributing_factors(self, data: dict[str, Any], events: list[Event]) -> list[dict[str, Any]]:
        """Identify contributing factors (NOT root cause per AREF terminology)."""
        factors = []

        if data.get("time_to_detect", 0) > 300:
            factors.append({
                "factor": "Delayed detection",
                "category": "detection",
                "description": "MTTD exceeded 5-minute target, delaying downstream response.",
            })

        affected = data.get("affected_services", [])
        if len(affected) > 2:
            factors.append({
                "factor": "Insufficient blast radius containment",
                "category": "absorption",
                "description": f"{len(affected)} services affected. Review isolation boundaries.",
            })

        adaptation_events = [e for e in events if e.category.value == "adaptation"]
        if not adaptation_events:
            factors.append({
                "factor": "No automated adaptation triggered",
                "category": "adaptation",
                "description": "System did not self-adjust. Review adaptation triggers.",
            })

        return factors

    def _assess_response(self, data: dict[str, Any], events: list[Event]) -> dict[str, Any]:
        return {
            "detection": "effective" if data.get("time_to_detect", 999) < 300 else "needs_improvement",
            "absorption": "effective" if data.get("blast_radius", {}).get("containment_pct", 0) > 95 else "needs_improvement",
            "adaptation": "effective" if len([e for e in events if e.category.value == "adaptation"]) > 0 else "needs_improvement",
            "recovery": "effective" if data.get("time_to_recover", 999) < 900 else "needs_improvement",
        }

    def _compute_detection_effectiveness(self, data: dict[str, Any]) -> float:
        mttd = data.get("time_to_detect", 0)
        if mttd == 0:
            return 1.0
        # Score 1.0 at 0s, 0.0 at 600s (10 min)
        return max(0, 1.0 - (mttd / 600))

    def _compute_adaptation_latency(self, events: list[Event]) -> float:
        detection_events = [e for e in events if e.category.value == "detection"]
        adaptation_events = [e for e in events if e.category.value == "adaptation"]
        if not detection_events or not adaptation_events:
            return 0
        return adaptation_events[0].timestamp - detection_events[0].timestamp

    def _extract_lessons(self, data: dict[str, Any], events: list[Event]) -> list[str]:
        lessons = []
        if data.get("time_to_detect", 0) > 300:
            lessons.append("Detection thresholds should be reviewed and tightened for this service.")
        if not any(e.category.value == "adaptation" for e in events):
            lessons.append("Automated adaptation was not triggered. Add or verify adaptation rules.")
        if data.get("time_to_recover", 0) > 900:
            lessons.append("Recovery exceeded 15-minute target. Review T0/T1 runbook automation.")
        if not lessons:
            lessons.append("Response was within targets. Document what went well for replication.")
        return lessons
