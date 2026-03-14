"""
✒ Metadata
    - Title: Base Service Factory (AREF Edition - v2.0)
    - File Name: base.py
    - Relative Path: services/base.py
    - Artifact Type: library
    - Version: 2.0.0
    - Date: 2026-03-13
    - Update: Thursday, March 13, 2026
    - Author: Dennis 'dnoice' Smaltz
    - A.I. Acknowledgement: Anthropic - Claude Opus 4
    - Signature: ︻デ═─── ✦ ✦ ✦ | Aim Twice, Shoot Once!
 
✒ Description:
    Shared FastAPI service factory that every AREF platform microservice is
    built through. The create_service() function returns a fully instrumented
    FastAPI application with Prometheus metrics, structured logging, health
    probes, correlation ID propagation, and AREF event bus lifecycle hooks.
 
✒ Key Features:
    - Feature 1: Single factory function (create_service) that wires all
                  cross-cutting concerns — call once per microservice
    - Feature 2: Async lifespan manager with configurable on_startup/on_shutdown
                  hooks, event bus publish on start/stop, and readiness gating
    - Feature 3: Prometheus auto-instrumentation via prometheus-fastapi-instrumentator
                  with excluded health/metrics endpoints and in-progress tracking
    - Feature 4: Observability middleware — per-request timing, status-class counting,
                  error rate tracking, correlation ID propagation (X-Request-ID /
                  X-Correlation-ID), and response time headers
    - Feature 5: Health endpoint (/health) with uptime, version, request/error counts,
                  error rate calculation, and resident memory reporting
    - Feature 6: Kubernetes-style liveness (/healthz) and readiness (/readyz) probes
                  with proper 503 response when not ready
    - Feature 7: Service info endpoint (/info) exposing metadata, dependencies,
                  Python version, platform, PID, and environment detection
    - Feature 8: Prometheus /metrics endpoint serving native metric exposition
    - Feature 9: CORS middleware configured for dashboard access
    - Feature 10: Shared metric registrations — SERVICE_REQUEST_COUNT, SERVICE_ERROR_COUNT,
                   SERVICE_UPTIME gauges labelled per service name
    - Feature 11: Best-effort memory reporting via resource.getrusage with macOS/Linux
                   byte-vs-KB normalization
    - Feature 12: Service metadata stored on app.state for downstream reference
 
✒ Usage Instructions:
    Import and call from any microservice:
 
        from services.base import create_service
 
        app = create_service(
            name="orders",
            description="Order lifecycle management",
            version="2.0.0",
            dependencies=["payments", "inventory"],
        )
 
    The returned app is a standard FastAPI instance with all middleware,
    health endpoints, and instrumentation already attached.
 
✒ Examples:
    # Minimal service
    app = create_service(name="gateway")
 
    # With dependencies and hooks
    async def setup(): ...
    async def teardown(): ...
    app = create_service(
        name="payments",
        version="2.0.0",
        dependencies=["postgres", "redis"],
        on_startup=setup,
        on_shutdown=teardown,
    )
 
✒ Other Important Information:
    - Dependencies:
        Required: fastapi, structlog, prometheus_client,
                  prometheus_fastapi_instrumentator
        Internal: aref.core.config, aref.core.events, aref.core.logging,
                  aref.core.metrics
    - Compatible platforms: Linux, macOS, Docker (Python 3.11+)
    - Environment variables:
        AREF_ENVIRONMENT — reported in /info endpoint ("local" if unset)
    - Performance notes: Middleware adds ~0.1ms overhead per request for
      timing and metric recording; memory reporting uses getrusage (no /proc)
    - Security considerations: CORS is wide-open — restrict in production;
      /info endpoint exposes PID and platform details
    - Known limitations: Memory reporting returns 0.0 on Windows; error rate
      is a simple count ratio (not windowed); no circuit breaker on dependency
      health checks
---------
"""

from __future__ import annotations

import inspect
import os
import platform
import sys
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Callable

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST
from prometheus_fastapi_instrumentator import Instrumentator

from aref.core.config import get_config
from aref.core.events import Event, EventCategory, get_event_bus
from aref.core.logging import setup_logging
from aref.core.metrics import SERVICE_UP, REQUEST_LATENCY, ERROR_RATE

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Shared metrics (instantiated once per process, labelled per service)
# ---------------------------------------------------------------------------
SERVICE_REQUEST_COUNT = Counter(
    "service_requests_total", "Total requests handled by service",
    ["service", "method", "status_class"],
)
SERVICE_ERROR_COUNT = Counter(
    "service_errors_total", "Total error responses (4xx/5xx) by service",
    ["service", "status_code"],
)
SERVICE_UPTIME = Gauge(
    "service_uptime_seconds", "Seconds since service started",
    ["service"],
)


def _get_memory_mb() -> float:
    """Best-effort resident memory in MB."""
    try:
        # Linux / macOS
        import resource
        rusage = resource.getrusage(resource.RUSAGE_SELF)
        # macOS reports bytes, Linux reports KB
        if sys.platform == "darwin":
            return rusage.ru_maxrss / (1024 * 1024)
        return rusage.ru_maxrss / 1024
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
def create_service(
    name: str,
    description: str = "",
    version: str = "1.0.0",
    dependencies: list[str] | None = None,
    on_startup: Callable | None = None,
    on_shutdown: Callable | None = None,
) -> FastAPI:
    """Factory for AREF-instrumented FastAPI services.

    Parameters
    ----------
    name : str
        Unique service identifier (e.g. ``"gateway"``, ``"orders"``).
    description : str
        Human-readable description shown in OpenAPI docs.
    version : str
        Semantic version of this service.
    dependencies : list[str] | None
        Names of services this one depends on (for health reporting).
    on_startup / on_shutdown : Callable | None
        Optional hooks called during lifespan management.
    """

    config = get_config()
    setup_logging(level=config.log_level)

    deps = dependencies or []
    _boot_time: dict[str, float] = {}   # mutable container so closures can write
    _ready: dict[str, bool] = {"value": False}
    _total_requests: dict[str, int] = {"count": 0}
    _total_errors: dict[str, int] = {"count": 0}

    # -----------------------------------------------------------------------
    # Lifespan
    # -----------------------------------------------------------------------
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        _boot_time["ts"] = time.time()
        logger.info("service.starting", service=name, version=version, python=platform.python_version())
        SERVICE_UP.labels(service=name).set(1)
        SERVICE_UPTIME.labels(service=name).set(0)

        bus = get_event_bus()
        await bus.publish(Event(
            category=EventCategory.SYSTEM,
            event_type="service_started",
            source=name,
            payload={"service": name, "version": version, "dependencies": deps},
        ))

        if on_startup:
            if inspect.iscoroutinefunction(on_startup):
                await on_startup()
            else:
                on_startup()

        _ready["value"] = True
        logger.info("service.ready", service=name)

        yield

        _ready["value"] = False
        SERVICE_UP.labels(service=name).set(0)

        await bus.publish(Event(
            category=EventCategory.SYSTEM,
            event_type="service_stopping",
            source=name,
            payload={"service": name, "uptime": round(time.time() - _boot_time.get("ts", 0), 1)},
        ))

        if on_shutdown:
            if inspect.iscoroutinefunction(on_shutdown):
                await on_shutdown()
            else:
                on_shutdown()

        logger.info("service.stopped", service=name)

    # -----------------------------------------------------------------------
    # App
    # -----------------------------------------------------------------------
    app = FastAPI(
        title=f"AREF | {name}",
        description=description or f"{name} microservice — AREF Platform",
        version=version,
        lifespan=lifespan,
    )

    # CORS for dashboard
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Prometheus auto-instrumentation
    Instrumentator(
        should_group_status_codes=True,
        should_instrument_requests_inprogress=True,
        excluded_handlers=["/health", "/healthz", "/readyz", "/metrics"],
        inprogress_name="aref_requests_inprogress",
        inprogress_labels=True,
    ).instrument(app)

    # -----------------------------------------------------------------------
    # Middleware stack (applied bottom-up, so first defined = outermost)
    # -----------------------------------------------------------------------

    @app.middleware("http")
    async def observability_middleware(request: Request, call_next: Callable) -> Response:
        """Combined timing, counting, error-tracking, and header propagation."""
        start = time.perf_counter()

        # Propagate or generate request ID
        request_id = request.headers.get("X-Request-ID") or request.headers.get("X-Correlation-ID", "")

        try:
            response = await call_next(request)
        except Exception:
            # Unhandled exception — log and return 500
            _total_errors["count"] += 1
            SERVICE_ERROR_COUNT.labels(service=name, status_code="500").inc()
            logger.exception("service.unhandled_exception", service=name, path=request.url.path)
            response = Response(content="Internal Server Error", status_code=500)

        elapsed = time.perf_counter() - start
        status = response.status_code
        status_class = f"{status // 100}xx"

        # Metrics
        REQUEST_LATENCY.labels(service=name, endpoint=request.url.path).observe(elapsed)
        SERVICE_REQUEST_COUNT.labels(service=name, method=request.method, status_class=status_class).inc()
        _total_requests["count"] += 1

        if status >= 400:
            SERVICE_ERROR_COUNT.labels(service=name, status_code=str(status)).inc()
            _total_errors["count"] += 1
            if status >= 500:
                ERROR_RATE.labels(service=name).inc()

        # Update uptime gauge
        if _boot_time.get("ts"):
            SERVICE_UPTIME.labels(service=name).set(round(time.time() - _boot_time["ts"], 1))

        # Response headers
        response.headers["X-Response-Time"] = f"{elapsed:.4f}"
        response.headers["X-Service"] = name
        if request_id:
            response.headers["X-Request-ID"] = request_id

        return response

    # -----------------------------------------------------------------------
    # Health / Readiness / Liveness endpoints
    # -----------------------------------------------------------------------

    @app.get("/health")
    async def health() -> dict[str, Any]:
        """Standard health check — includes uptime, version, and basic stats."""
        uptime = round(time.time() - _boot_time.get("ts", time.time()), 1)
        return {
            "service": name,
            "status": "healthy" if _ready["value"] else "starting",
            "version": version,
            "uptime_seconds": uptime,
            "total_requests": _total_requests["count"],
            "total_errors": _total_errors["count"],
            "error_rate": round(_total_errors["count"] / max(_total_requests["count"], 1), 4),
            "memory_mb": round(_get_memory_mb(), 1),
            "timestamp": time.time(),
        }

    @app.get("/healthz")
    async def liveness() -> dict[str, str]:
        """Kubernetes-style liveness probe — process is alive."""
        return {"status": "alive"}

    @app.get("/readyz")
    async def readiness() -> Response:
        """Kubernetes-style readiness probe — service is ready to accept traffic."""
        if _ready["value"]:
            return Response(content='{"status":"ready"}', status_code=200, media_type="application/json")
        return Response(content='{"status":"not_ready"}', status_code=503, media_type="application/json")

    @app.get("/info")
    async def info() -> dict[str, Any]:
        """Service metadata — useful for service discovery and dashboards."""
        uptime = round(time.time() - _boot_time.get("ts", time.time()), 1)
        return {
            "service": name,
            "description": description,
            "version": version,
            "dependencies": deps,
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "uptime_seconds": uptime,
            "ready": _ready["value"],
            "environment": os.environ.get("AREF_ENVIRONMENT", "local"),
            "pid": os.getpid(),
        }

    # -----------------------------------------------------------------------
    # Prometheus metrics endpoint
    # -----------------------------------------------------------------------

    @app.get("/metrics")
    async def metrics() -> Response:
        return Response(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST,
        )

    # Store service metadata on the app for reference
    app.state.service_name = name
    app.state.service_version = version
    app.state.service_dependencies = deps

    return app
