"""
Maturity Model and CRS Scoring Engine.

Computes:
  - Per-pillar maturity levels (1-5)
  - Composite Resilience Score (CRS) with configurable weight profiles
  - Gap analysis between current and target maturity
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

from aref.core.config import CRS_WEIGHT_PROFILES, RiskProfile, get_config
from aref.core.metrics import CRS_SCORE, PILLAR_MATURITY
from aref.core.models import MaturityLevel

logger = structlog.get_logger(__name__)

PILLAR_NAMES = ["detection", "absorption", "adaptation", "recovery", "evolution"]


@dataclass
class PillarAssessment:
    """Assessment result for a single pillar."""
    pillar: str
    level: MaturityLevel = MaturityLevel.REACTIVE
    score: float = 1.0  # 1.0-5.0 for fractional scoring
    evidence: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class MaturityReport:
    """Full maturity assessment report."""
    assessments: dict[str, PillarAssessment] = field(default_factory=dict)
    crs_scores: dict[str, float] = field(default_factory=dict)
    overall_level: MaturityLevel = MaturityLevel.REACTIVE
    target_level: MaturityLevel = MaturityLevel.DEFINED

    @property
    def average_score(self) -> float:
        if not self.assessments:
            return 1.0
        return sum(a.score for a in self.assessments.values()) / len(self.assessments)


class MaturityAssessor:
    """
    Evaluates organizational maturity across all five AREF pillars.
    Uses data from the metrics engine, detection, absorption, etc.
    """

    def __init__(self) -> None:
        self._criteria: dict[str, list[dict[str, Any]]] = self._build_criteria()

    def _build_criteria(self) -> dict[str, list[dict[str, Any]]]:
        """Build assessment criteria for each pillar at each level."""
        return {
            "detection": [
                {"level": 1, "criterion": "No formal monitoring", "check": lambda ctx: ctx.get("sli_count", 0) == 0},
                {"level": 2, "criterion": "Basic uptime monitoring", "check": lambda ctx: ctx.get("sli_count", 0) >= 1},
                {"level": 3, "criterion": "SLIs defined, anomaly detection active", "check": lambda ctx: ctx.get("sli_count", 0) >= 5 and ctx.get("anomaly_detection", False)},
                {"level": 4, "criterion": "ML anomaly detection, < 5min MTTD", "check": lambda ctx: ctx.get("mttd", 999) < 300},
                {"level": 5, "criterion": "Predictive detection, proactive alerting", "check": lambda ctx: ctx.get("predictive", False)},
            ],
            "absorption": [
                {"level": 1, "criterion": "No circuit breakers or bulkheads", "check": lambda ctx: ctx.get("circuit_breakers", 0) == 0},
                {"level": 2, "criterion": "Some circuit breakers deployed", "check": lambda ctx: ctx.get("circuit_breakers", 0) >= 1},
                {"level": 3, "criterion": "Blast radius mapped, > 80% containment", "check": lambda ctx: ctx.get("containment_pct", 0) >= 80},
                {"level": 4, "criterion": "Automated containment, > 95%", "check": lambda ctx: ctx.get("containment_pct", 0) >= 95},
                {"level": 5, "criterion": "Antifragile — gains from controlled failures", "check": lambda ctx: ctx.get("chaos_experiments", 0) >= 10},
            ],
            "adaptation": [
                {"level": 1, "criterion": "Manual response only", "check": lambda ctx: ctx.get("auto_adaptations", 0) == 0},
                {"level": 2, "criterion": "Some auto-scaling", "check": lambda ctx: ctx.get("auto_scaling", False)},
                {"level": 3, "criterion": "Feature flags, traffic shifting", "check": lambda ctx: ctx.get("feature_flags", 0) >= 5},
                {"level": 4, "criterion": "< 30s adaptation latency", "check": lambda ctx: ctx.get("adaptation_latency", 999) < 30},
                {"level": 5, "criterion": "Self-healing, predictive adaptation", "check": lambda ctx: ctx.get("self_healing", False)},
            ],
            "recovery": [
                {"level": 1, "criterion": "Ad-hoc recovery, no runbooks", "check": lambda ctx: ctx.get("runbook_count", 0) == 0},
                {"level": 2, "criterion": "Runbooks exist, inconsistent use", "check": lambda ctx: ctx.get("runbook_count", 0) >= 1},
                {"level": 3, "criterion": "Quarterly drills, tiered recovery", "check": lambda ctx: ctx.get("drills_per_year", 0) >= 4},
                {"level": 4, "criterion": "Automated T0, MTTR < 15 min", "check": lambda ctx: ctx.get("mttr", 999) < 900},
                {"level": 5, "criterion": "Continuous recovery testing, < 5 min MTTR", "check": lambda ctx: ctx.get("mttr", 999) < 300},
            ],
            "evolution": [
                {"level": 1, "criterion": "No post-incident reviews", "check": lambda ctx: ctx.get("review_count", 0) == 0},
                {"level": 2, "criterion": "Occasional post-mortems", "check": lambda ctx: ctx.get("review_count", 0) >= 1},
                {"level": 3, "criterion": "> 85% action completion, blameless culture", "check": lambda ctx: ctx.get("action_completion_rate", 0) >= 85},
                {"level": 4, "criterion": "> 8 actions/quarter, < 10% recurrence", "check": lambda ctx: ctx.get("actions_per_quarter", 0) >= 8},
                {"level": 5, "criterion": "Predictive learning, org-wide sharing < 72h", "check": lambda ctx: ctx.get("knowledge_share_hours", 999) < 72},
            ],
        }

    def assess(self, context: dict[str, dict[str, Any]]) -> MaturityReport:
        """Run full maturity assessment across all pillars."""
        report = MaturityReport()

        for pillar in PILLAR_NAMES:
            pillar_ctx = context.get(pillar, {})
            assessment = self._assess_pillar(pillar, pillar_ctx)
            report.assessments[pillar] = assessment
            PILLAR_MATURITY.labels(pillar=pillar).set(assessment.score)

        # Compute CRS for all risk profiles
        pillar_scores = {p: a.score for p, a in report.assessments.items()}
        for profile in RiskProfile:
            crs = self._compute_crs(pillar_scores, profile)
            report.crs_scores[profile.value] = crs
            CRS_SCORE.labels(risk_profile=profile.value).set(crs)

        # Overall level = minimum pillar level (weakest link)
        min_score = min(a.score for a in report.assessments.values())
        report.overall_level = MaturityLevel(int(min_score))

        return report

    def _assess_pillar(self, pillar: str, context: dict[str, Any]) -> PillarAssessment:
        criteria = self._criteria.get(pillar, [])
        achieved_level = 1

        evidence = []
        gaps = []

        for criterion in criteria:
            level = criterion["level"]
            passes = criterion["check"](context)
            if passes and level <= 2:
                # Levels 1-2 criteria are "you are at this level IF this condition"
                achieved_level = max(achieved_level, level)
                evidence.append(criterion["criterion"])
            elif passes:
                achieved_level = max(achieved_level, level)
                evidence.append(criterion["criterion"])
            elif level > achieved_level:
                gaps.append(f"Level {level}: {criterion['criterion']}")

        return PillarAssessment(
            pillar=pillar,
            level=MaturityLevel(achieved_level),
            score=float(achieved_level),
            evidence=evidence,
            gaps=gaps,
        )

    def _compute_crs(self, pillar_scores: dict[str, float], profile: RiskProfile) -> float:
        """CRS = SUM(w_i * M_i), i=1..5"""
        weights = CRS_WEIGHT_PROFILES[profile]
        score = sum(weights[p] * pillar_scores.get(p, 1.0) for p in PILLAR_NAMES)
        return round(score, 3)
