"""
✒ Metadata
    - Title: AREF Control Plane API (AREF Edition - v2.0)
    - File Name: app.py
    - Relative Path: aref/dashboard/app.py
    - Artifact Type: script
    - Version: 2.0.0
    - Date: 2026-03-13
    - Update: Thursday, March 13, 2026
    - Author: Dennis 'dnoice' Smaltz
    - A.I. Acknowledgement: Anthropic - Claude Opus 4
    - Signature: ︻デ═─── ✦ ✦ ✦ | Aim Twice, Shoot Once!

✒ Description:
    Central FastAPI application serving both the AREF web dashboard and the
    REST API that powers every pillar of the Adaptive Resilience Engineering
    Framework. Initializes and wires all five pillar engines—Detection,
    Absorption, Adaptation, Recovery, and Evolution—plus chaos engineering
    controls, maturity assessment, and Prometheus metrics export.

✒ Key Features:
    - Feature 1: Async lifespan manager bootstraps all AREF engines on startup
    - Feature 2: Detection subsystem wiring — synthetic probes, SLI/SLO definitions,
                  anomaly metric streams, threshold rules, and a background data feed
                  that polls live microservices every 10 seconds
    - Feature 3: Absorption subsystem wiring — circuit breakers per service→dependency
                  pair, rate limiters, bulkheads, blast radius dependency graph, and
                  four-tier graceful degradation paths per service
    - Feature 4: Adaptation subsystem wiring — feature flags (essential + non-essential),
                  traffic routes (primary + backup per service), and auto-scaler configs
    - Feature 5: Evolution seed data — incident patterns for recurrence matching,
                  knowledge base entries with past incident learnings, seeded post-incident
                  reviews, and tracked action items across all five pillars
    - Feature 6: REST API surface covering aggregate status, per-pillar deep-dive
                  endpoints, service health checks, alert feeds, event timeline,
                  maturity assessment, and full metrics with CRS and error budgets
    - Feature 7: Chaos engineering API — start/stop fault injection experiments
                  with rollback support
    - Feature 8: Prometheus /metrics endpoint for external monitoring integration
    - Feature 9: CORS-enabled with static file serving for the dashboard SPA
    - Feature 10: Docker-aware service URL resolution (localhost vs container names)

✒ Usage Instructions:
    Start the server with uvicorn:
        $ uvicorn aref.dashboard.app:app --host 0.0.0.0 --port 9000

    Or via Docker Compose (preferred for full microservice stack):
        $ docker compose up dashboard

    API documentation auto-generated at:
        http://localhost:9000/docs  (Swagger UI)
        http://localhost:9000/redoc (ReDoc)

✒ Examples:
    $ curl http://localhost:9000/api/aref/status
    $ curl http://localhost:9000/api/aref/detection
    $ curl http://localhost:9000/api/aref/absorption
    $ curl http://localhost:9000/api/aref/adaptation
    $ curl http://localhost:9000/api/aref/recovery
    $ curl http://localhost:9000/api/aref/evolution
    $ curl http://localhost:9000/api/aref/maturity
    $ curl http://localhost:9000/api/aref/metrics
    $ curl -X POST http://localhost:9000/api/aref/chaos/start -d '{"experiment":"gateway-latency"}'
    $ curl -X POST http://localhost:9000/api/aref/chaos/stop

✒ Other Important Information:
    - Dependencies:
        Required: fastapi, uvicorn, httpx, structlog, prometheus_client
        Internal: aref.core, aref.detection, aref.absorption, aref.adaptation,
                  aref.recovery, aref.evolution, aref.maturity, chaos
    - Compatible platforms: Linux, macOS, Docker (Python 3.11+)
    - Environment variables:
        AREF_ENVIRONMENT=docker  — switches service URLs to container hostnames
    - Performance notes: Background data feed polls every 10s; API responses are
      non-blocking async; engine startup takes ~2s for warm-up
    - Security considerations: CORS is wide-open (allow_origins=["*"]) — restrict
      in production deployments; no authentication on API endpoints
    - Known limitations: Pillar scores use simplified heuristics; maturity context
      is partially hardcoded for demo purposes; chaos experiments require the full
      microservice stack to be running
---------
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator

import asyncio
import os
import random

import httpx
import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response

from aref.core.config import get_config
from aref.core.events import Event, EventCategory, EventSeverity, get_event_bus
from aref.core.logging import setup_logging
from aref.core.metrics import get_metrics_engine
from aref.dashboard.engines import get_engines

from aref.detection.engine import DetectionEngine
from aref.detection.threshold import ThresholdRule
from aref.detection.anomaly import MetricStream
from aref.detection.synthetic import ProbeTarget
from aref.detection.sli_tracker import SLI, SLO
from aref.absorption.circuit_breaker import CircuitBreaker, get_circuit_breaker_registry
from aref.absorption.bulkhead import BulkheadManager
from aref.absorption.rate_limiter import RateLimiterManager
from aref.absorption.blast_radius import BlastRadiusAnalyzer, DependencyNode
from aref.absorption.degradation import (
    DegradationManager, DegradationLevel, DegradationTier, ServiceDegradation,
)
from aref.adaptation.engine import AdaptationEngine
from aref.adaptation.feature_flags import FeatureFlag
from aref.adaptation.traffic_shifter import TrafficRoute
from aref.adaptation.decision_tree import STRATEGY_RISK
from aref.recovery.engine import RecoveryEngine
from aref.evolution.engine import EvolutionEngine
from aref.maturity.model import MaturityAssessor
from chaos.injector import FaultInjector, FaultType
from chaos.experiments import EXPERIMENTS, ExperimentRunner

logger = structlog.get_logger(__name__)

# Paths
STATIC_DIR = Path(__file__).parent / "static"
TEMPLATE_DIR = Path(__file__).parent / "templates"

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    e = get_engines()

    config = get_config()
    setup_logging(level=config.log_level)
    bus = get_event_bus()

    # Initialize engines
    e.detection_engine = DetectionEngine(bus)
    e.adaptation_engine = AdaptationEngine(bus)
    e.recovery_engine = RecoveryEngine(bus)
    e.evolution_engine = EvolutionEngine(bus)
    e.fault_injector = FaultInjector()
    e.experiment_runner = ExperimentRunner(e.fault_injector)
    e.maturity_assessor = MaturityAssessor()
    e.rate_limiter_mgr = RateLimiterManager()
    e.bulkhead_mgr = BulkheadManager()
    e.blast_radius = BlastRadiusAnalyzer()
    e.degradation_mgr = DegradationManager()

    # Start engines
    await e.detection_engine.start()
    await e.adaptation_engine.start()
    await e.recovery_engine.start()
    await e.evolution_engine.start()

    # ----- Wire up detection subsystems with live data -----
    _docker = os.environ.get("AREF_ENVIRONMENT") == "docker"

    def _svc_url(name: str, port: int) -> str:
        host = name if _docker else "localhost"
        return f"http://{host}:{port}"

    services = {
        "gateway":       _svc_url("gateway", 8000),
        "orders":        _svc_url("orders", 8001),
        "payments":      _svc_url("payments", 8002),
        "inventory":     _svc_url("inventory", 8003),
        "notifications": _svc_url("notifications", 8004),
    }

    # 1) Synthetic probes — active health checks against every service
    for name, base_url in services.items():
        e.detection_engine.synthetic.add_target(
            ProbeTarget(service=name, url=f"{base_url}/health", timeout=5.0)
        )

    # 2) SLI/SLO definitions — availability + latency per service
    for name in services:
        # Availability SLI
        avail_sli = SLI(name="availability", service=name, unit="ratio",
                        description=f"{name} availability ratio")
        e.detection_engine.sli_tracker.register_sli(avail_sli)

        avail_slo = SLO(name="availability", sli_name="availability",
                        service=name, target=0.999,
                        description=f"{name} 99.9% availability SLO")
        e.detection_engine.sli_tracker.register_slo(avail_slo)

        # Latency SLI
        lat_sli = SLI(name="latency_p99", service=name, unit="ms",
                       description=f"{name} p99 latency")
        e.detection_engine.sli_tracker.register_sli(lat_sli)

        lat_slo = SLO(name="latency_p99", sli_name="latency_p99",
                       service=name, target=0.995,
                       description=f"{name} latency SLO (p99 < 500ms)")
        e.detection_engine.sli_tracker.register_slo(lat_slo)

    # 3) Anomaly metric streams — latency and error rate per service
    for name in services:
        e.detection_engine.anomaly.register_stream(
            MetricStream(name="response_latency", service=name,
                         window_size=100, z_score_threshold=3.0,
                         description=f"{name} response latency (ms)")
        )
        e.detection_engine.anomaly.register_stream(
            MetricStream(name="error_rate", service=name,
                         window_size=100, z_score_threshold=3.0,
                         description=f"{name} error rate (pct)")
        )

    # 4) Threshold rules — shared state dict holds latest metric values
    _live_metrics: dict[str, float] = {}

    for name in services:
        # Error rate threshold
        _err_key = f"{name}.error_rate"
        e.detection_engine.threshold.add_rule(ThresholdRule(
            name=f"{name}_error_rate",
            service=name,
            metric_fn=lambda k=_err_key: _live_metrics.get(k),
            warning_threshold=5.0,    # > 5% error rate = warning
            critical_threshold=15.0,  # > 15% = critical
            consecutive_samples=3,
            description=f"{name} error rate percentage",
        ))

        # Latency threshold
        _lat_key = f"{name}.latency"
        e.detection_engine.threshold.add_rule(ThresholdRule(
            name=f"{name}_latency",
            service=name,
            metric_fn=lambda k=_lat_key: _live_metrics.get(k),
            warning_threshold=300.0,   # > 300ms = warning
            critical_threshold=1000.0, # > 1s = critical
            consecutive_samples=3,
            description=f"{name} response latency (ms)",
        ))

    # 5) Background task: poll services, feed data into all subsystems
    async def _detection_data_feed() -> None:
        """Periodically poll services and record metrics into detection subsystems."""
        await asyncio.sleep(2)  # let services warm up
        async with httpx.AsyncClient(timeout=5.0) as client:
            while True:
                for name, base_url in services.items():
                    try:
                        start = time.perf_counter()
                        resp = await client.get(f"{base_url}/health")
                        latency_ms = (time.perf_counter() - start) * 1000.0

                        healthy = resp.status_code == 200
                        # Simulate a small jitter error rate based on real health
                        error_rate = 0.0 if healthy else random.uniform(20.0, 50.0)
                        # Add small natural jitter to healthy services
                        if healthy:
                            error_rate = random.uniform(0.0, 2.0)

                        # Feed threshold rules
                        _live_metrics[f"{name}.latency"] = latency_ms
                        _live_metrics[f"{name}.error_rate"] = error_rate

                        # Feed anomaly streams
                        e.detection_engine.anomaly.record(name, "response_latency", latency_ms)
                        e.detection_engine.anomaly.record(name, "error_rate", error_rate)

                        # Feed SLI tracker
                        e.detection_engine.sli_tracker.record_sli(
                            name, "availability", 1.0 if healthy else 0.0
                        )
                        e.detection_engine.sli_tracker.record_sli(
                            name, "latency_p99", latency_ms
                        )

                        # Record downtime if unhealthy (probe interval worth)
                        if not healthy:
                            e.detection_engine.sli_tracker.record_downtime(
                                name, "availability", 10.0
                            )
                            e.detection_engine.sli_tracker.record_downtime(
                                name, "latency_p99", 10.0
                            )

                    except Exception:
                        # Service unreachable — record as error
                        _live_metrics[f"{name}.latency"] = 5000.0
                        _live_metrics[f"{name}.error_rate"] = 100.0
                        e.detection_engine.anomaly.record(name, "response_latency", 5000.0)
                        e.detection_engine.anomaly.record(name, "error_rate", 100.0)
                        e.detection_engine.sli_tracker.record_sli(name, "availability", 0.0)
                        e.detection_engine.sli_tracker.record_downtime(name, "availability", 10.0)

                await asyncio.sleep(10)  # poll every 10 seconds

    _feed_task = asyncio.create_task(_detection_data_feed())

    # ----- Wire up absorption subsystems with live data -----
    cb_registry = get_circuit_breaker_registry()

    # Circuit breakers — one per service→dependency pair
    service_deps = {
        "gateway": ["orders", "payments", "inventory", "notifications"],
        "orders": ["payments", "inventory", "notifications"],
        "payments": ["postgres", "redis"],
        "inventory": ["postgres", "redis"],
        "notifications": ["redis"],
    }
    for svc, deps in service_deps.items():
        for dep in deps:
            cb = CircuitBreaker(
                name=f"{svc}->{dep}",
                service=svc,
                dependency=dep,
                failure_threshold=config.absorption.circuit_breaker_failure_threshold,
                recovery_timeout=config.absorption.circuit_breaker_recovery_timeout,
                half_open_max_calls=config.absorption.circuit_breaker_half_open_max,
            )
            cb_registry.register(cb)

    # Rate limiters — per service
    for svc_name in services:
        e.rate_limiter_mgr.create(
            name=svc_name,
            rate=config.absorption.rate_limit_requests_per_second,
            capacity=config.absorption.rate_limit_burst,
        )

    # Bulkheads — per service
    for svc_name in services:
        e.bulkhead_mgr.create(
            name=svc_name,
            max_concurrent=config.absorption.bulkhead_max_concurrent,
        )

    # Blast radius dependency graph
    infra_nodes = {
        "postgres": ("database", "critical"),
        "redis": ("cache", "high"),
    }
    for svc_name in services:
        e.blast_radius.register_node(DependencyNode(
            name=svc_name,
            node_type="service",
            criticality="critical" if svc_name == "gateway" else "high",
            failure_modes=["timeout", "error_rate_spike", "crash"],
            degradation_tiers=["full", "reduced", "minimal", "emergency"],
        ))
    for infra_name, (ntype, crit) in infra_nodes.items():
        e.blast_radius.register_node(DependencyNode(
            name=infra_name,
            node_type=ntype,
            criticality=crit,
            failure_modes=["connection_refused", "timeout", "data_corruption"],
        ))
    for svc, deps in service_deps.items():
        for dep in deps:
            e.blast_radius.register_dependency(svc, dep)

    # Degradation tiers — per service
    for svc_name in services:
        svc_deg = ServiceDegradation(
            service=svc_name,
            tiers=[
                DegradationTier(DegradationLevel.FULL, "Full",
                                f"{svc_name} — all features operational"),
                DegradationTier(DegradationLevel.REDUCED, "Reduced",
                                f"{svc_name} — non-essential features disabled",
                                disabled_features=["analytics", "recommendations"],
                                reduced_capacity_pct=75.0),
                DegradationTier(DegradationLevel.MINIMAL, "Minimal",
                                f"{svc_name} — core functionality only",
                                disabled_features=["analytics", "recommendations", "search", "exports"],
                                reduced_capacity_pct=40.0),
                DegradationTier(DegradationLevel.EMERGENCY, "Emergency",
                                f"{svc_name} — read-only / static responses",
                                disabled_features=["analytics", "recommendations", "search", "exports", "writes"],
                                reduced_capacity_pct=10.0),
            ],
        )
        e.degradation_mgr.register_service(svc_deg)

    # ----- Wire up adaptation subsystems with live data -----

    # Feature flags — per service (essential + non-essential)
    flag_defs = [
        ("analytics", False, "Usage analytics and telemetry"),
        ("recommendations", False, "Personalized recommendations"),
        ("search", False, "Full-text search functionality"),
        ("experimental", False, "Experimental features"),
        ("core_api", True, "Core API endpoints"),
        ("auth", True, "Authentication and authorization"),
    ]
    for svc_name in services:
        for flag_name, critical, desc in flag_defs:
            e.adaptation_engine.feature_flags.register(FeatureFlag(
                name=f"{svc_name}.{flag_name}",
                service=svc_name,
                enabled=True,
                critical=critical,
                description=f"{svc_name} — {desc}",
            ))

    # Traffic routes — primary + backup per service
    for svc_name in services:
        e.adaptation_engine.traffic_shifter.register_routes(svc_name, [
            TrafficRoute(target=f"{svc_name}-primary", weight=100, healthy=True),
            TrafficRoute(target=f"{svc_name}-backup", weight=0, healthy=True),
        ])

    # Auto-scaler — instance counts per service
    for svc_name in services:
        e.adaptation_engine.scaler.register_service(
            service=svc_name, current=1, min_instances=1, max_instances=10,
        )

    # Load evolution seed data (patterns, KB entries, reviews, action items)
    from aref.dashboard.seed_data import load_seed_data
    await load_seed_data(e.evolution_engine)

    logger.info("aref.platform.started", version="2.0.0")

    yield

    # Cancel data feed
    _feed_task.cancel()

    # Shutdown
    await e.detection_engine.stop()
    await e.adaptation_engine.stop()
    await e.recovery_engine.stop()
    await e.evolution_engine.stop()

    logger.info("aref.platform.stopped")


# Create the FastAPI app
app = FastAPI(
    title="AREF Control Plane",
    description="Adaptive Resilience Engineering Framework — Dashboard & API",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return (TEMPLATE_DIR / "index.html").read_text()


# ---------------------------------------------------------------------------
# Status API
# ---------------------------------------------------------------------------

@app.get("/api/aref/status")
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


@app.get("/api/aref/services")
async def get_services() -> dict[str, Any]:
    """Get health of all microservices with enriched dependency and resilience data."""
    e = get_engines()
    import os
    import httpx
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


@app.get("/api/aref/alerts")
async def get_alerts() -> dict[str, Any]:
    e = get_engines()
    if e.detection_engine:
        return {
            "alerts": e.detection_engine.get_active_alerts(),
            "stats": e.detection_engine.get_alert_stats(),
        }
    return {"alerts": [], "stats": {}}


@app.get("/api/aref/timeline")
async def get_timeline() -> dict[str, Any]:
    bus = get_event_bus()
    events = bus.get_history(limit=100)
    event_dicts = [e.to_dict() for e in events]

    categories: dict[str, int] = {}
    severities: dict[str, int] = {}
    sources: dict[str, int] = {}
    for e in event_dicts:
        cat = e.get("category", "unknown")
        sev = e.get("severity", "info")
        src = e.get("source", "unknown")
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


# ---------------------------------------------------------------------------
# Pillar APIs
# ---------------------------------------------------------------------------

@app.get("/api/aref/detection")
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


@app.get("/api/aref/absorption")
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


@app.get("/api/aref/adaptation")
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


@app.get("/api/aref/recovery")
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


@app.get("/api/aref/evolution")
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


@app.get("/api/aref/maturity")
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


@app.get("/api/aref/metrics")
async def get_aref_metrics() -> dict[str, Any]:
    e = get_engines()
    from aref.core.config import CRS_WEIGHT_PROFILES, RiskProfile
    from aref.core.metrics import MetricsEngine

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


# ---------------------------------------------------------------------------
# Chaos API
# ---------------------------------------------------------------------------

@app.post("/api/aref/chaos/start")
async def start_chaos(request: Request) -> dict[str, Any]:
    eng = get_engines()
    if not eng.fault_injector:
        return {"error": "Chaos module not initialized"}
    body = await request.json()
    experiment_name = body.get("experiment", "")

    exp = next((x for x in EXPERIMENTS if x.name == experiment_name), None)
    if not exp:
        return {"error": f"Unknown experiment: {experiment_name}"}

    injection = await eng.fault_injector.inject(
        target_service=exp.target_service,
        fault_type=exp.fault_type,
        rate=exp.fault_rate,
        duration=exp.duration,
        parameters=exp.parameters,
    )
    return {"status": "started", "injection": injection.injection_id, "experiment": experiment_name}


@app.post("/api/aref/chaos/stop")
async def stop_chaos() -> dict[str, Any]:
    eng = get_engines()
    if not eng.fault_injector:
        return {"error": "Chaos module not initialized"}
    count = await eng.fault_injector.rollback_all()
    return {"status": "stopped", "rolled_back": count}


@app.get("/api/aref/chaos/status")
async def chaos_status() -> dict[str, Any]:
    eng = get_engines()
    if not eng.fault_injector:
        return {"active": []}
    return eng.fault_injector.get_status()


# ---------------------------------------------------------------------------
# Prometheus
# ---------------------------------------------------------------------------

@app.get("/metrics")
async def prometheus_metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
