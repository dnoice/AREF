"""
✒ Metadata
    - Title: Pillar Deep-Dive Routes (AREF Edition - v2.0)
    - File Name: pillars.py
    - Relative Path: aref/dashboard/routes/pillars.py
    - Artifact Type: script
    - Version: 2.0.0
    - Date: 2026-03-13
    - Update: Thursday, March 13, 2026
    - Author: Dennis 'dnoice' Smaltz
    - A.I. Acknowledgement: Anthropic - Claude Opus 4
    - Signature: ︻デ═─── ✦ ✦ ✦ | Aim Twice, Shoot Once!

✒ Description:
    FastAPI router for per-pillar deep-dive endpoints covering Detection,
    Absorption, Adaptation, Recovery, and Evolution. Each endpoint returns
    detailed subsystem status, configuration, and operational history.

✒ Key Features:
    - Feature 1: Detection status with threshold, anomaly, synthetic, and SLI data
    - Feature 2: Absorption status with circuit breakers, rate limiters, bulkheads,
                  blast radius, and degradation tiers
    - Feature 3: Adaptation status with feature flags, traffic shifting, scaling,
                  and decision tree strategies
    - Feature 4: Recovery status with runbook catalog, execution history, and
                  tier target definitions
    - Feature 5: Evolution status with reviews, action items, pattern matching,
                  knowledge base, and review process metadata

✒ Usage Instructions:
    Included in app.py via app.include_router(pillars_router)
---------
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from aref.core.config import get_config
from aref.absorption.circuit_breaker import get_circuit_breaker_registry
from aref.adaptation.decision_tree import STRATEGY_RISK
from aref.dashboard.engines import get_engines

router = APIRouter()


@router.get("/api/aref/detection")
async def get_detection_status() -> dict[str, Any]:
    e = get_engines()
    if not e.detection_engine:
        return {"status": "not_running"}
    config = get_config().detection
    return {
        "status": "running" if e.detection_engine._running else "stopped",
        "alerts": e.detection_engine.get_alert_stats(),
        "active_alerts": e.detection_engine.get_active_alerts(),
        "threshold": e.detection_engine.threshold.get_status(),
        "anomaly": e.detection_engine.anomaly.get_stream_stats(),
        "synthetic": e.detection_engine.synthetic.get_status(),
        "sli_tracker": e.detection_engine.sli_tracker.get_summary(),
        "config": {
            "mttd_target": config.mttd_target_seconds,
            "threshold_interval": config.threshold_check_interval,
            "anomaly_interval": config.anomaly_check_interval,
            "synthetic_interval": config.synthetic_probe_interval,
            "fatigue_max_weekly": config.alert_fatigue_max_per_week,
            "alert_to_action_target": config.alert_to_action_ratio,
            "correlation_window": config.change_correlation_window,
        },
    }


@router.get("/api/aref/absorption")
async def get_absorption_status() -> dict[str, Any]:
    e = get_engines()
    config = get_config().absorption
    registry = get_circuit_breaker_registry()
    return {
        "circuit_breakers": registry.get_status(),
        "rate_limiters": e.rate_limiter_mgr.get_status() if e.rate_limiter_mgr else {},
        "bulkheads": e.bulkhead_mgr.get_status() if e.bulkhead_mgr else {},
        "blast_radius": e.blast_radius.get_dependency_map() if e.blast_radius else {},
        "blast_radius_assessments": e.blast_radius.get_assessments() if e.blast_radius else [],
        "degradation": e.degradation_mgr.get_status() if e.degradation_mgr else {},
        "config": {
            "blast_radius_target_pct": config.blast_radius_target_pct,
            "circuit_breaker_failure_threshold": config.circuit_breaker_failure_threshold,
            "circuit_breaker_recovery_timeout": config.circuit_breaker_recovery_timeout,
            "bulkhead_max_concurrent": config.bulkhead_max_concurrent,
            "rate_limit_rps": config.rate_limit_requests_per_second,
            "rate_limit_burst": config.rate_limit_burst,
        },
    }


@router.get("/api/aref/adaptation")
async def get_adaptation_status() -> dict[str, Any]:
    e = get_engines()
    if not e.adaptation_engine:
        return {"status": "not_running"}
    config = get_config().adaptation
    base = e.adaptation_engine.get_status()
    base["scaler"] = e.adaptation_engine.scaler.get_status()
    base["decision_tree_strategies"] = STRATEGY_RISK
    base["adaptation_history"] = e.adaptation_engine._history[-30:]
    base["config"] = {
        "latency_target": config.latency_target_seconds,
        "scale_up_cpu": config.scale_up_cpu_threshold,
        "scale_down_cpu": config.scale_down_cpu_threshold,
        "traffic_shift_health": config.traffic_shift_health_threshold,
        "feature_flag_eb_trigger": config.feature_flag_error_budget_trigger,
        "adaptation_window": config.adaptation_window_seconds,
    }
    return base


@router.get("/api/aref/recovery")
async def get_recovery_status() -> dict[str, Any]:
    e = get_engines()
    if not e.recovery_engine:
        return {"status": "not_running"}
    config = get_config().recovery
    base = e.recovery_engine.get_status()

    # Runbook catalog
    runbooks = []
    for rb in e.recovery_engine.runbook_executor._runbooks:
        runbooks.append({
            "name": rb.name,
            "service": rb.service,
            "tier": rb.recovery_tier.name,
            "tier_value": rb.recovery_tier.value,
            "description": rb.description,
            "steps_count": len(rb.steps),
            "steps": [
                {
                    "order": s.order,
                    "action": s.action,
                    "description": s.description,
                    "role": s.role,
                    "automated": s.automated,
                    "timeout": s.timeout_seconds,
                }
                for s in rb.steps
            ],
            "version": rb.version,
            "last_drilled": rb.last_drilled,
        })
    base["runbooks"] = runbooks

    # Execution history
    base["execution_history"] = e.recovery_engine.runbook_executor.get_execution_history()[-20:]

    # Recovery history
    base["recovery_history"] = e.recovery_engine._history[-20:]

    # Tier definitions from config
    base["tier_targets"] = {
        "T0_EMERGENCY": {"target_seconds": config.t0_target_seconds, "label": "Emergency Stabilization", "range": "0-5 min"},
        "T1_MINIMUM": {"target_seconds": config.t1_target_seconds, "label": "Minimum Viable Recovery", "range": "5-15 min"},
        "T2_FUNCTIONAL": {"target_seconds": config.t2_target_seconds, "label": "Functional Recovery", "range": "15-60 min"},
        "T3_FULL": {"target_seconds": config.t3_target_seconds, "label": "Full Restoration", "range": "1-4 hours"},
        "T4_HARDENING": {"target_seconds": config.t4_target_days * 86400, "label": "Post-Incident Hardening", "range": "1-2 weeks"},
    }

    base["config"] = {
        "mttr_target": config.mttr_target_seconds,
        "t0_target": config.t0_target_seconds,
        "t1_target": config.t1_target_seconds,
        "t2_target": config.t2_target_seconds,
        "t3_target": config.t3_target_seconds,
        "t4_target_days": config.t4_target_days,
        "drill_interval_days": config.runbook_drill_interval_days,
    }
    return base


@router.get("/api/aref/evolution")
async def get_evolution_status() -> dict[str, Any]:
    e = get_engines()
    if not e.evolution_engine:
        return {"status": "not_running"}

    config = get_config().evolution
    base = e.evolution_engine.get_status()

    # Enrich reviews with full detail
    base["reviews"] = e.evolution_engine._reviews[-20:]

    # Enrich action items with per-item detail
    all_items = list(e.evolution_engine.action_tracker._items.values())
    base["action_items"] = [
        {
            "action_id": a.action_id,
            "incident_id": a.incident_id,
            "title": a.title,
            "description": a.description,
            "priority": a.priority,
            "status": a.status,
            "pillar": a.pillar,
            "created_at": a.created_at,
            "completed_at": a.completed_at,
            "due_date": a.due_date,
            "is_overdue": a.is_overdue,
        }
        for a in all_items
    ]

    # Patterns
    base["patterns"] = e.evolution_engine.pattern_matcher._patterns
    base["recurrence_rate"] = e.evolution_engine.pattern_matcher.get_recurrence_rate()

    # Knowledge base entries
    base["knowledge_base_entries"] = e.evolution_engine.knowledge_base._entries[-20:]

    # Six-step review process metadata
    base["review_process"] = [
        {"step": 1, "name": "Timeline Reconstruction", "description": "Reconstruct chronological event sequence from detection through resolution"},
        {"step": 2, "name": "Contributing Factor Analysis", "description": "Identify systemic factors (not root cause) that enabled the incident"},
        {"step": 3, "name": "Response Effectiveness", "description": "Assess each pillar's effectiveness during the incident lifecycle"},
        {"step": 4, "name": "Action Item Generation", "description": "Generate tracked, prioritized improvement actions per pillar"},
        {"step": 5, "name": "Knowledge Dissemination", "description": "Share learnings within 72 hours per blueprint requirement"},
        {"step": 6, "name": "Systemic Pattern Matching", "description": "Cross-reference against knowledge base to detect recurrence"},
    ]

    base["config"] = {
        "improvement_velocity_target": config.improvement_velocity_target,
        "action_completion_rate_target": config.action_completion_rate_target,
        "recurrence_rate_target": config.recurrence_rate_target,
        "knowledge_share_target_hours": config.knowledge_share_target_hours,
        "review_deadline_hours": config.post_incident_review_deadline_hours,
    }
    return base
