"""
Blast Radius Analysis — Blueprint Section 3.2.2.

Maps dependencies, failure modes, and impact scope across three levels:
  - Component: Single service (reviewed every release)
  - Service: Service cluster/domain (reviewed monthly)
  - Organization: Business unit/product (reviewed quarterly)

Key finding from blueprint: Teams with up-to-date blast radius docs
recover 40-60% faster during incidents.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from aref.core.metrics import BLAST_RADIUS_CONTAINED

logger = structlog.get_logger(__name__)


@dataclass
class DependencyNode:
    """A service or component in the dependency graph."""
    name: str
    node_type: str = "service"  # service, database, cache, queue, external
    criticality: str = "high"   # critical, high, medium, low
    dependencies: list[str] = field(default_factory=list)
    dependents: list[str] = field(default_factory=list)
    failure_modes: list[str] = field(default_factory=list)
    degradation_tiers: list[str] = field(default_factory=list)


@dataclass
class BlastRadiusAssessment:
    """Result of a blast radius analysis for an incident."""
    incident_id: str
    failed_component: str
    timestamp: float = field(default_factory=time.time)
    directly_affected: list[str] = field(default_factory=list)
    indirectly_affected: list[str] = field(default_factory=list)
    contained_services: list[str] = field(default_factory=list)
    uncontained_services: list[str] = field(default_factory=list)
    containment_pct: float = 0.0
    estimated_user_impact_pct: float = 0.0
    estimated_revenue_impact: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "failed_component": self.failed_component,
            "directly_affected": self.directly_affected,
            "indirectly_affected": self.indirectly_affected,
            "containment_pct": round(self.containment_pct, 1),
            "user_impact_pct": round(self.estimated_user_impact_pct, 1),
            "revenue_impact": round(self.estimated_revenue_impact, 2),
        }


class BlastRadiusAnalyzer:
    """
    Analyzes failure blast radius by traversing the dependency graph.
    Computes containment percentage for the Absorption pillar's key metric.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, DependencyNode] = {}
        self._assessments: list[BlastRadiusAssessment] = []

    def register_node(self, node: DependencyNode) -> None:
        self._nodes[node.name] = node

    def register_dependency(self, source: str, target: str) -> None:
        if source in self._nodes:
            if target not in self._nodes[source].dependencies:
                self._nodes[source].dependencies.append(target)
        if target in self._nodes:
            if source not in self._nodes[target].dependents:
                self._nodes[target].dependents.append(source)

    def analyze(
        self,
        failed_component: str,
        incident_id: str = "",
        containment_mechanisms: list[str] | None = None,
    ) -> BlastRadiusAssessment:
        """
        Analyze blast radius for a failed component.
        Traverses dependency graph to find all affected services.
        """
        containment = containment_mechanisms or []

        # BFS to find all affected nodes
        directly_affected: list[str] = []
        indirectly_affected: list[str] = []
        visited = {failed_component}
        queue = [(failed_component, 0)]

        while queue:
            current, depth = queue.pop(0)
            node = self._nodes.get(current)
            if not node:
                continue

            for dependent in node.dependents:
                if dependent not in visited:
                    visited.add(dependent)
                    if depth == 0:
                        directly_affected.append(dependent)
                    else:
                        indirectly_affected.append(dependent)
                    queue.append((dependent, depth + 1))

        # Determine containment
        all_affected = directly_affected + indirectly_affected
        contained = [s for s in all_affected if s in containment or self._has_fallback(s)]
        uncontained = [s for s in all_affected if s not in contained]

        total = len(all_affected)
        containment_pct = (len(contained) / total * 100) if total > 0 else 100.0

        assessment = BlastRadiusAssessment(
            incident_id=incident_id,
            failed_component=failed_component,
            directly_affected=directly_affected,
            indirectly_affected=indirectly_affected,
            contained_services=contained,
            uncontained_services=uncontained,
            containment_pct=containment_pct,
        )

        self._assessments.append(assessment)
        if incident_id:
            BLAST_RADIUS_CONTAINED.labels(incident_id=incident_id).set(containment_pct)

        logger.info(
            "blast_radius.analyzed",
            failed=failed_component,
            affected=len(all_affected),
            containment_pct=f"{containment_pct:.1f}%",
        )

        return assessment

    def _has_fallback(self, service: str) -> bool:
        node = self._nodes.get(service)
        if not node:
            return False
        return len(node.degradation_tiers) > 1

    def get_dependency_map(self) -> dict[str, Any]:
        return {
            name: {
                "type": node.node_type,
                "criticality": node.criticality,
                "dependencies": node.dependencies,
                "dependents": node.dependents,
                "failure_modes": node.failure_modes,
            }
            for name, node in self._nodes.items()
        }

    def get_assessments(self) -> list[dict[str, Any]]:
        return [a.to_dict() for a in self._assessments]
