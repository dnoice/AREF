"""
Incident Knowledge Base — Blueprint Section 3.5.1 Step 6.

Stores structured incident data and reviews for pattern matching and organizational learning.
"""

from __future__ import annotations

import time
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class KnowledgeBase:
    """Structured repository of incident knowledge."""

    def __init__(self) -> None:
        self._entries: list[dict[str, Any]] = []

    def store_incident(self, incident_data: dict[str, Any], review: dict[str, Any]) -> None:
        entry = {
            "stored_at": time.time(),
            "incident_id": incident_data.get("incident_id", ""),
            "service": incident_data.get("source_service", ""),
            "severity": incident_data.get("severity", ""),
            "detection_class": incident_data.get("detection_class", ""),
            "contributing_factors": review.get("contributing_factors", []),
            "lessons_learned": review.get("lessons_learned", []),
            "response_effectiveness": review.get("response_effectiveness", {}),
            "mttd": incident_data.get("time_to_detect"),
            "mttr": incident_data.get("time_to_recover"),
        }
        self._entries.append(entry)

    def search(self, service: str | None = None, severity: str | None = None) -> list[dict[str, Any]]:
        results = self._entries
        if service:
            results = [e for e in results if e.get("service") == service]
        if severity:
            results = [e for e in results if e.get("severity") == severity]
        return results

    @property
    def size(self) -> int:
        return len(self._entries)

    def get_lessons_for_service(self, service: str) -> list[str]:
        lessons = []
        for entry in self._entries:
            if entry.get("service") == service:
                lessons.extend(entry.get("lessons_learned", []))
        return lessons
