"""
✒ Metadata
    - Title: Status & Service Routes (AREF Edition - v2.0)
    - File Name: status.py
    - Relative Path: aref/dashboard/routes/status.py
    - Artifact Type: script
    - Version: 2.0.0
    - Date: 2026-03-13
    - Update: Thursday, March 13, 2026
    - Author: Dennis 'dnoice' Smaltz
    - A.I. Acknowledgement: Anthropic - Claude Opus 4
    - Signature: ︻デ═─── ✦ ✦ ✦ | Aim Twice, Shoot Once!

✒ Description:
    FastAPI router for aggregate status, service health, active alerts,
    and event timeline endpoints. Provides the top-level operational view
    of the AREF platform.

✒ Key Features:
    - Feature 1: Aggregate CRS and pillar scores with real engine data
    - Feature 2: Per-service health with dependency graph, circuit breakers,
                  degradation levels, rate limiters, and scaling instances
    - Feature 3: Active alert feed from the detection engine
    - Feature 4: Event timeline with category/severity/source summaries

✒ Usage Instructions:
    Included in app.py via app.include_router(status_router)
---------
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx
from fastapi import APIRouter

from aref.core.config import get_config
from aref.core.events import get_event_bus
from aref.absorption.circuit_breaker import get_circuit_breaker_registry
from aref.dashboard.engines import get_engines

router = APIRouter()


@router.get("/api/aref/status")
async def get_status() -> dict[str, Any]:
    """Aggregate status across all AREF pillars."""
    e = get_engines()
    config = get_config()

    pillar_scores = {
        "detection": 2.5,
        "absorption": 2.0,
        "adaptation": 2.0,
        "recovery": 2.5,
        "evolution": 1.5,
    }

    # If engines are running, get real data
    if e.detection_engine:
        alert_stats = e.detection_engine.get_alert_stats()
        pillar_scores["detection"] = min(5.0, 2.0 + (1.0 if alert_stats["total_alerts"] > 0 else 0))

    if e.recovery_engine:
        rec_status = e.recovery_engine.get_status()
        pillar_scores["recovery"] = min(5.0, 2.0 + (1.0 if rec_status["total_recovered"] > 0 else 0))

    if e.evolution_engine:
        evo_status = e.evolution_engine.get_status()
        pillar_scores["evolution"] = min(5.0, 1.5 + (1.0 if evo_status["total_reviews"] > 0 else 0))

    crs = sum(
        config.crs_weights[p] * pillar_scores.get(p, 1.0)
        for p in pillar_scores
    )

    return {
        "crs": round(crs, 3),
        "risk_profile": config.risk_profile.value,
        "pillars": pillar_scores,
        "maturity": {p: int(s) for p, s in pillar_scores.items()},
        "chaos_active": bool(e.fault_injector and e.fault_injector.get_active()),
        "timestamp": time.time(),
    }


@router.get("/api/aref/services")
async def get_services() -> dict[str, Any]:
    """Get health of all microservices with enriched dependency and resilience data."""
    e = get_engines()
    _docker = os.environ.get("AREF_ENVIRONMENT") == "docker"
    services_config = {
        "gateway": {"url": f"http://{'gateway' if _docker else 'localhost'}:8000", "port": 8000,
                     "description": "API Gateway — rate limiting, tracing, routing"},
        "orders": {"url": f"http://{'orders' if _docker else 'localhost'}:8001", "port": 8001,
                   "description": "Order management and orchestration"},
        "payments": {"url": f"http://{'payments' if _docker else 'localhost'}:8002", "port": 8002,
                     "description": "Payment processing and transactions"},
        "inventory": {"url": f"http://{'inventory' if _docker else 'localhost'}:8003", "port": 8003,
                      "description": "Stock management and availability checks"},
        "notifications": {"url": f"http://{'notifications' if _docker else 'localhost'}:8004", "port": 8004,
                          "description": "Event-driven notifications (email, push)"},
    }

    results = {}
    async with httpx.AsyncClient(timeout=3.0) as client:
        for name, cfg in services_config.items():
            try:
                resp = await client.get(f"{cfg['url']}/health")
                health = resp.json()
            except Exception:
                health = {"service": name, "status": "unreachable", "timestamp": time.time()}
            results[name] = {
                **health,
                "port": cfg["port"],
                "description": cfg["description"],
            }

    # Enrich with dependency graph from blast radius analyzer
    blast_analyzer = e.blast_radius
    dep_graph = {}
    if blast_analyzer:
        for node_name, node in blast_analyzer._nodes.items():
            dep_graph[node_name] = {
                "type": node.node_type,
                "criticality": node.criticality,
                "dependencies": node.dependencies,
                "dependents": node.dependents,
                "failure_modes": node.failure_modes,
            }

    # Circuit breaker states per service
    registry = get_circuit_breaker_registry()
    cb_status = registry.get_status()
    service_cbs = {}
    for cb_name, cb_info in cb_status.get("breakers", {}).items():
        svc = cb_info.get("service", "")
        if svc not in service_cbs:
            service_cbs[svc] = []
        service_cbs[svc].append({
            "name": cb_name,
            "dependency": cb_info.get("dependency", ""),
            "state": cb_info.get("state", "unknown"),
            "failure_count": cb_info.get("failure_count", 0),
            "success_count": cb_info.get("success_count", 0),
        })

    # Degradation levels per service
    svc_degradation = {}
    if e.degradation_mgr:
        for svc_name, svc_deg in e.degradation_mgr._services.items():
            svc_degradation[svc_name] = {
                "current_level": svc_deg.current_level.name.lower(),
                "tiers": len(svc_deg.tiers),
            }

    # Rate limiters per service
    svc_rate_limiters = {}
    if e.rate_limiter_mgr:
        for rl_name, rl in e.rate_limiter_mgr._limiters.items():
            svc_rate_limiters[rl_name] = {
                "rate": rl.rate,
                "capacity": rl.capacity,
                "tokens": round(rl._tokens, 1),
            }

    # Auto-scaler instances
    svc_instances = {}
    if e.adaptation_engine:
        for svc_name in results:
            svc_instances[svc_name] = e.adaptation_engine.scaler.get_instances(svc_name)

    return {
        "services": results,
        "dependency_graph": dep_graph,
        "circuit_breakers_by_service": service_cbs,
        "degradation": svc_degradation,
        "rate_limiters": svc_rate_limiters,
        "instances": svc_instances,
        "infrastructure": {
            "postgres": dep_graph.get("postgres", {}),
            "redis": dep_graph.get("redis", {}),
        },
    }


@router.get("/api/aref/alerts")
async def get_alerts() -> dict[str, Any]:
    e = get_engines()
    if e.detection_engine:
        return {
            "alerts": e.detection_engine.get_active_alerts(),
            "stats": e.detection_engine.get_alert_stats(),
        }
    return {"alerts": [], "stats": {}}


@router.get("/api/aref/timeline")
async def get_timeline() -> dict[str, Any]:
    bus = get_event_bus()
    events = bus.get_history(limit=100)
    event_dicts = [ev.to_dict() for ev in events]

    categories: dict[str, int] = {}
    severities: dict[str, int] = {}
    sources: dict[str, int] = {}
    for ev in event_dicts:
        cat = ev.get("category", "unknown")
        sev = ev.get("severity", "info")
        src = ev.get("source", "unknown")
        categories[cat] = categories.get(cat, 0) + 1
        severities[sev] = severities.get(sev, 0) + 1
        sources[src] = sources.get(src, 0) + 1

    return {
        "events": event_dicts,
        "summary": {
            "total": len(event_dicts),
            "by_category": categories,
            "by_severity": severities,
            "by_source": sources,
        },
    }
