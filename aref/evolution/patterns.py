"""
Incident Pattern Matching — Blueprint Section 3.5.2.

Cross-references incidents against the knowledge base to detect recurrence.
Target: < 10% recurrence rate.
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class PatternMatcher:
    """Detects recurring incident patterns by comparing attributes."""

    def __init__(self) -> None:
        self._patterns: list[dict[str, Any]] = []

    def register_pattern(self, pattern: dict[str, Any]) -> None:
        self._patterns.append(pattern)

    def find_matches(self, incident_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Find patterns matching the given incident."""
        matches = []
        service = incident_data.get("source_service", "")
        detection_class = incident_data.get("detection_class", "")

        for pattern in self._patterns:
            score = 0
            if pattern.get("service") == service:
                score += 3
            if pattern.get("detection_class") == detection_class:
                score += 2
            if pattern.get("severity") == incident_data.get("severity"):
                score += 1

            # Match on similar contributing factors
            pattern_factors = set(pattern.get("contributing_factors", []))
            incident_factors = set(incident_data.get("contributing_factors", []))
            if pattern_factors & incident_factors:
                score += 2

            if score >= 3:
                matches.append({
                    "pattern": pattern,
                    "match_score": score,
                    "matching_attributes": {
                        "service": pattern.get("service") == service,
                        "detection_class": pattern.get("detection_class") == detection_class,
                    },
                })

        return matches

    def extract_pattern(self, incident_data: dict[str, Any]) -> dict[str, Any]:
        """Extract a pattern from a resolved incident for future matching."""
        pattern = {
            "service": incident_data.get("source_service", ""),
            "detection_class": incident_data.get("detection_class", ""),
            "severity": incident_data.get("severity", ""),
            "contributing_factors": incident_data.get("contributing_factors", []),
            "affected_services": incident_data.get("affected_services", []),
            "created_from": incident_data.get("incident_id", ""),
        }
        self._patterns.append(pattern)
        return pattern

    def get_recurrence_rate(self) -> float:
        if not self._patterns:
            return 0.0
        # Count patterns that have matched at least once
        matched = sum(1 for p in self._patterns if p.get("_match_count", 0) > 0)
        return (matched / len(self._patterns)) * 100
