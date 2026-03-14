"""
✒ Metadata
    - Title: Maturity & Metrics Routes (AREF Edition - v2.0)
    - File Name: metrics.py
    - Relative Path: aref/dashboard/routes/metrics.py
    - Artifact Type: script
    - Version: 2.0.0
    - Date: 2026-03-13
    - Update: Thursday, March 13, 2026
    - Author: Dennis 'dnoice' Smaltz
    - A.I. Acknowledgement: Anthropic - Claude Opus 4
    - Signature: ︻デ═─── ✦ ✦ ✦ | Aim Twice, Shoot Once!

✒ Description:
    FastAPI router for maturity assessment and comprehensive AREF metrics
    endpoints. Provides CRS scores across all risk profiles, error budget
    calculations, and pillar-level maturity gaps.

✒ Key Features:
    - Feature 1: Full maturity assessment with L1-L5 per-pillar scoring
    - Feature 2: CRS computation across all four risk profiles
    - Feature 3: Error budget calculations for 99.0%, 99.5%, and 99.9% SLOs
    - Feature 4: MTTD, MTTR, availability, and target comparison

✒ Usage Instructions:
    Included in app.py via app.include_router(metrics_router)
---------
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from aref.core.config import get_config, CRS_WEIGHT_PROFILES, RiskProfile
from aref.core.metrics import get_metrics_engine, MetricsEngine
from aref.dashboard.engines import get_engines

router = APIRouter()


@router.get("/api/aref/maturity")
async def get_maturity() -> dict[str, Any]:
    e = get_engines()
    if not e.maturity_assessor:
        return {"status": "not_running"}
    context = {
        "detection": {"sli_count": 5, "anomaly_detection": True, "mttd": 180},
        "absorption": {"circuit_breakers": 3, "containment_pct": 85},
        "adaptation": {"auto_scaling": True, "feature_flags": 8, "adaptation_latency": 25},
        "recovery": {"runbook_count": 5, "drills_per_year": 4, "mttr": 600},
        "evolution": {"review_count": 3, "action_completion_rate": 80, "actions_per_quarter": 6},
    }
    report = e.maturity_assessor.assess(context)
    return {
        "assessments": {p: {"level": a.level.value, "score": a.score, "gaps": a.gaps} for p, a in report.assessments.items()},
        "crs_scores": report.crs_scores,
        "overall_level": report.overall_level.value,
    }


@router.get("/api/aref/metrics")
async def get_aref_metrics() -> dict[str, Any]:
    e = get_engines()
    engine = get_metrics_engine()
    config = get_config()
    summary = engine.get_summary()

    # Compute CRS across all risk profiles
    pillar_scores = {
        "detection": 2.0, "absorption": 2.0, "adaptation": 2.0,
        "recovery": 2.0, "evolution": 1.5,
    }
    if e.detection_engine:
        stats = e.detection_engine.get_alert_stats()
        pillar_scores["detection"] = min(5.0, 2.0 + (1.0 if stats["total_alerts"] > 0 else 0))
    if e.recovery_engine:
        rec = e.recovery_engine.get_status()
        pillar_scores["recovery"] = min(5.0, 2.0 + (1.0 if rec["total_recovered"] > 0 else 0))
    if e.evolution_engine:
        evo = e.evolution_engine.get_status()
        pillar_scores["evolution"] = min(5.0, 1.5 + (1.0 if evo["total_reviews"] > 0 else 0))

    crs_profiles = {}
    for profile in RiskProfile:
        weights = CRS_WEIGHT_PROFILES[profile]
        crs_profiles[profile.value] = {
            "crs": MetricsEngine.compute_crs(pillar_scores, profile),
            "weights": weights,
        }

    # Error budget calculations (30-day window)
    window_30d = 30 * 24 * 3600
    slo_tiers = {
        "99.9%": 0.999,
        "99.5%": 0.995,
        "99.0%": 0.990,
    }
    total_downtime = sum(engine._downtime_intervals) if engine._downtime_intervals else 0
    error_budgets = {}
    for label, slo in slo_tiers.items():
        budget_total = (1 - slo) * window_30d
        consumed = min(total_downtime, budget_total)
        remaining = budget_total - consumed
        error_budgets[label] = {
            "slo": slo,
            "budget_total_seconds": round(budget_total, 1),
            "consumed_seconds": round(consumed, 1),
            "remaining_seconds": round(remaining, 1),
            "remaining_pct": round((remaining / budget_total) * 100, 1) if budget_total > 0 else 100.0,
        }

    return {
        **summary,
        "targets": {
            "mttd": config.detection.mttd_target_seconds,
            "mttr": config.recovery.mttr_target_seconds,
            "blast_radius": config.absorption.blast_radius_target_pct,
            "adaptation_latency": config.adaptation.latency_target_seconds,
            "improvement_velocity": config.evolution.improvement_velocity_target,
            "availability_slo": 99.9,
        },
        "pillar_scores": pillar_scores,
        "crs_profiles": crs_profiles,
        "current_profile": config.risk_profile.value,
        "error_budgets": error_budgets,
        "uptime_seconds": sum(engine._uptime_intervals) if engine._uptime_intervals else 0,
        "downtime_seconds": total_downtime,
    }
