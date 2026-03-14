"""
✒ Metadata
    - Title: Subsystem Bootstrap Wiring (AREF Edition - v2.0)
    - File Name: bootstrap.py
    - Relative Path: aref/dashboard/bootstrap.py
    - Artifact Type: script
    - Version: 2.0.0
    - Date: 2026-03-13
    - Update: Thursday, March 13, 2026
    - Author: Dennis 'dnoice' Smaltz
    - A.I. Acknowledgement: Anthropic - Claude Opus 4
    - Signature: ︻デ═─── ✦ ✦ ✦ | Aim Twice, Shoot Once!

✒ Description:
    Wires all three subsystem layers (Detection, Absorption, Adaptation) with
    live configuration data during dashboard lifespan startup. Registers
    probes, SLIs, threshold rules, circuit breakers, rate limiters, bulkheads,
    blast radius graph, degradation tiers, feature flags, traffic routes, and
    auto-scaler configs.

✒ Key Features:
    - Feature 1: Detection wiring — synthetic probes, SLI/SLO definitions,
                  anomaly metric streams, threshold rules, and background
                  data feed task
    - Feature 2: Absorption wiring — circuit breakers per service→dependency,
                  rate limiters, bulkheads, blast radius graph, degradation tiers
    - Feature 3: Adaptation wiring — feature flags (essential + non-essential),
                  traffic routes (primary + backup), auto-scaler configs
    - Feature 4: Docker-aware service URL resolution
    - Feature 5: Returns background feed task handle for cancellation on shutdown

✒ Usage Instructions:
    Called from app.py lifespan:
        services, live_metrics, feed_task = await wire_subsystems(engines, config)
---------
"""

from __future__ import annotations

import asyncio
import os

from aref.core.config import AREFConfig
from aref.detection.threshold import ThresholdRule
from aref.detection.anomaly import MetricStream
from aref.detection.synthetic import ProbeTarget
from aref.detection.sli_tracker import SLI, SLO
from aref.absorption.circuit_breaker import CircuitBreaker, get_circuit_breaker_registry
from aref.absorption.blast_radius import DependencyNode
from aref.absorption.degradation import (
    DegradationLevel, DegradationTier, ServiceDegradation,
)
from aref.adaptation.feature_flags import FeatureFlag
from aref.adaptation.traffic_shifter import TrafficRoute
from aref.dashboard.engines import EngineContainer
from aref.dashboard.background import detection_data_feed


# Service dependency map
SERVICE_DEPS = {
    "gateway": ["orders", "payments", "inventory", "notifications"],
    "orders": ["payments", "inventory", "notifications"],
    "payments": ["postgres", "redis"],
    "inventory": ["postgres", "redis"],
    "notifications": ["redis"],
}


async def wire_subsystems(
    engines: EngineContainer,
    config: AREFConfig,
) -> tuple[dict[str, str], dict[str, float], asyncio.Task]:
    """Wire detection, absorption, and adaptation subsystems. Returns
    (services dict, live_metrics dict, background feed task)."""

    # ----- Service URL resolution -----
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

    # ── Detection subsystem wiring ────────────────────────────────────

    # 1) Synthetic probes — active health checks against every service
    for name, base_url in services.items():
        engines.detection_engine.synthetic.add_target(
            ProbeTarget(service=name, url=f"{base_url}/health", timeout=5.0)
        )

    # 2) SLI/SLO definitions — availability + latency per service
    for name in services:
        avail_sli = SLI(name="availability", service=name, unit="ratio",
                        description=f"{name} availability ratio")
        engines.detection_engine.sli_tracker.register_sli(avail_sli)

        avail_slo = SLO(name="availability", sli_name="availability",
                        service=name, target=0.999,
                        description=f"{name} 99.9% availability SLO")
        engines.detection_engine.sli_tracker.register_slo(avail_slo)

        lat_sli = SLI(name="latency_p99", service=name, unit="ms",
                       description=f"{name} p99 latency")
        engines.detection_engine.sli_tracker.register_sli(lat_sli)

        lat_slo = SLO(name="latency_p99", sli_name="latency_p99",
                       service=name, target=0.995,
                       description=f"{name} latency SLO (p99 < 500ms)")
        engines.detection_engine.sli_tracker.register_slo(lat_slo)

    # 3) Anomaly metric streams — latency and error rate per service
    for name in services:
        engines.detection_engine.anomaly.register_stream(
            MetricStream(name="response_latency", service=name,
                         window_size=100, z_score_threshold=3.0,
                         description=f"{name} response latency (ms)")
        )
        engines.detection_engine.anomaly.register_stream(
            MetricStream(name="error_rate", service=name,
                         window_size=100, z_score_threshold=3.0,
                         description=f"{name} error rate (pct)")
        )

    # 4) Threshold rules — shared state dict holds latest metric values
    live_metrics: dict[str, float] = {}

    for name in services:
        _err_key = f"{name}.error_rate"
        engines.detection_engine.threshold.add_rule(ThresholdRule(
            name=f"{name}_error_rate",
            service=name,
            metric_fn=lambda k=_err_key: live_metrics.get(k),
            warning_threshold=5.0,
            critical_threshold=15.0,
            consecutive_samples=3,
            description=f"{name} error rate percentage",
        ))

        _lat_key = f"{name}.latency"
        engines.detection_engine.threshold.add_rule(ThresholdRule(
            name=f"{name}_latency",
            service=name,
            metric_fn=lambda k=_lat_key: live_metrics.get(k),
            warning_threshold=300.0,
            critical_threshold=1000.0,
            consecutive_samples=3,
            description=f"{name} response latency (ms)",
        ))

    # 5) Background data feed task
    feed_task = asyncio.create_task(
        detection_data_feed(engines, services, live_metrics)
    )

    # ── Absorption subsystem wiring ───────────────────────────────────

    cb_registry = get_circuit_breaker_registry()
    for svc, deps in SERVICE_DEPS.items():
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

    for svc_name in services:
        engines.rate_limiter_mgr.create(
            name=svc_name,
            rate=config.absorption.rate_limit_requests_per_second,
            capacity=config.absorption.rate_limit_burst,
        )

    for svc_name in services:
        engines.bulkhead_mgr.create(
            name=svc_name,
            max_concurrent=config.absorption.bulkhead_max_concurrent,
        )

    # Blast radius dependency graph
    infra_nodes = {
        "postgres": ("database", "critical"),
        "redis": ("cache", "high"),
    }
    for svc_name in services:
        engines.blast_radius.register_node(DependencyNode(
            name=svc_name,
            node_type="service",
            criticality="critical" if svc_name == "gateway" else "high",
            failure_modes=["timeout", "error_rate_spike", "crash"],
            degradation_tiers=["full", "reduced", "minimal", "emergency"],
        ))
    for infra_name, (ntype, crit) in infra_nodes.items():
        engines.blast_radius.register_node(DependencyNode(
            name=infra_name,
            node_type=ntype,
            criticality=crit,
            failure_modes=["connection_refused", "timeout", "data_corruption"],
        ))
    for svc, deps in SERVICE_DEPS.items():
        for dep in deps:
            engines.blast_radius.register_dependency(svc, dep)

    # Degradation tiers
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
        engines.degradation_mgr.register_service(svc_deg)

    # ── Adaptation subsystem wiring ───────────────────────────────────

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
            engines.adaptation_engine.feature_flags.register(FeatureFlag(
                name=f"{svc_name}.{flag_name}",
                service=svc_name,
                enabled=True,
                critical=critical,
                description=f"{svc_name} — {desc}",
            ))

    for svc_name in services:
        engines.adaptation_engine.traffic_shifter.register_routes(svc_name, [
            TrafficRoute(target=f"{svc_name}-primary", weight=100, healthy=True),
            TrafficRoute(target=f"{svc_name}-backup", weight=0, healthy=True),
        ])

    for svc_name in services:
        engines.adaptation_engine.scaler.register_service(
            service=svc_name, current=1, min_instances=1, max_instances=10,
        )

    return services, live_metrics, feed_task
