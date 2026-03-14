"""
✒ Metadata
    - Title: API Gateway Service (AREF Edition - v2.0)
    - File Name: gateway_app.py
    - Relative Path: services/gateway/gateway_app.py
    - Artifact Type: script
    - Version: 2.0.0
    - Date: 2026-03-13
    - Update: Thursday, March 13, 2026
    - Author: Dennis 'dnoice' Smaltz
    - A.I. Acknowledgement: Anthropic - Claude Opus 4
    - Signature: ︻デ═─── ✦ ✦ ✦ | Aim Twice, Shoot Once!
 
✒ Description:
    Front-door API gateway for all client requests into the AREF microservice
    platform. Handles request routing to downstream services with retry and
    exponential backoff, correlation ID injection, gateway-level circuit
    breaker awareness, deep health aggregation, and a full order creation
    pipeline (inventory check → order create → payment → notification).
 
✒ Key Features:
    - Feature 1: Service registry with per-service timeout, retry count, and
                  Docker-aware URL resolution (container names vs localhost)
    - Feature 2: Retry with exponential backoff and jitter — configurable per
                  service, with AREF event bus CRITICAL-severity events on
                  exhaustion and WARNING-severity on circuit open
    - Feature 3: Gateway-level circuit breaker awareness — per-service failure
                  tracking within a 30-second sliding window, 5-failure trip
                  threshold, half-open recovery on success
    - Feature 4: Tracing middleware — generates or propagates correlation IDs
                  (X-Correlation-ID), tracks per-route request counts and
                  end-to-end latency histogram, maintains rolling request log
    - Feature 5: Four-step order creation pipeline — inventory check, order
                  create, payment processing, and notification (fire-and-forget)
                  — with per-step latency tracking and graceful degradation
                  when non-critical services are unavailable
    - Feature 6: Deep health aggregation (/api/gateway/health/deep) — probes
                  every registered downstream service, reports per-service
                  status/latency/circuit state, and overall system health
    - Feature 7: Gateway statistics — throughput, error rate, average and p99
                  latency from the rolling request log, circuit breaker states
    - Feature 8: Proxy endpoints — transparent pass-through to inventory stock,
                  payment lookup, and provider health for dashboard access
    - Feature 9: Prometheus metrics — gateway_requests_total (by method/route/
                  status), gateway_request_latency_seconds histogram, retry
                  counter (by target), circuit open gauge (by target)
    - Feature 10: Chaos injection — error and latency fault modes at the
                   gateway level for AREF chaos experiments
    - Feature 11: Rolling request log (last 200 requests) with method, path,
                   status, latency, correlation ID, and timestamp
    - Feature 12: Order and order list proxy endpoints with correlation ID
                   propagation to the orders service
 
✒ Usage Instructions:
    Start via uvicorn:
        $ uvicorn services.gateway.gateway_app:app --host 0.0.0.0 --port 8000
 
    Or via Docker Compose as part of the AREF microservice stack.
 
✒ Examples:
    # Create order (full pipeline)
    $ curl -X POST http://localhost:8000/api/orders \
        -d '{"items":[{"sku":"WIDGET-001","quantity":2}],"total":19.98,"customer_email":"test@example.com"}'
 
    # Get order (proxied)
    $ curl http://localhost:8000/api/orders/ORD-ABCD1234
 
    # Deep health check
    $ curl http://localhost:8000/api/gateway/health/deep
 
    # Gateway stats
    $ curl http://localhost:8000/api/gateway/stats
 
    # Recent requests
    $ curl http://localhost:8000/api/gateway/requests?limit=20
 
    # Proxy: inventory stock
    $ curl http://localhost:8000/api/inventory/stock
 
    # Proxy: provider health
    $ curl http://localhost:8000/api/payments/providers/health
 
    # Enable chaos
    $ curl -X POST http://localhost:8000/chaos/enable \
        -d '{"type":"latency","rate":0.3,"delay":2.0}'
 
✒ Other Important Information:
    - Dependencies:
        Required: fastapi, httpx, structlog, prometheus_client
        Internal: services.base, aref.core.events
    - Compatible platforms: Linux, macOS, Docker (Python 3.11+)
    - Environment variables:
        AREF_ENVIRONMENT=docker — switches service URLs to container hostnames
    - Performance notes: Shared httpx.AsyncClient with 10s timeout and 5s
      connect timeout; retry backoff starts at 100ms with 2x multiplier;
      rolling request log bounded at 200 entries
    - Security considerations: No authentication; CORS inherited from base
      factory; correlation IDs auto-generated if not provided
    - Known limitations: Gateway circuit breaker is simplified (failure count
      in sliding window, not full state machine); no request body size limits;
      notification step is fire-and-forget; httpx client not closed on shutdown
---------
"""

from __future__ import annotations

import asyncio
import os
import random
import time
import uuid
from typing import Any

import httpx
import structlog
from fastapi import HTTPException, Request, Response
from prometheus_client import Counter, Gauge, Histogram

from services.base import create_service
from aref.core.events import Event, EventCategory, EventSeverity, get_event_bus

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# App + metrics
# ---------------------------------------------------------------------------
app = create_service(
    name="gateway",
    description="API Gateway with rate limiting, tracing, retry, and intelligent routing",
)

GATEWAY_REQUESTS = Counter(
    "gateway_requests_total", "Gateway requests by route and status",
    ["method", "route", "status"],
)
GATEWAY_LATENCY = Histogram(
    "gateway_request_latency_seconds", "End-to-end gateway latency",
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)
GATEWAY_RETRIES = Counter(
    "gateway_retries_total", "Retry attempts by target service",
    ["target"],
)
GATEWAY_CIRCUIT_OPEN = Gauge(
    "gateway_circuit_open", "Whether gateway considers a service circuit-open",
    ["target"],
)

# ---------------------------------------------------------------------------
# Service registry + HTTP client
# ---------------------------------------------------------------------------
_docker = os.environ.get("AREF_ENVIRONMENT") == "docker"
SERVICE_REGISTRY: dict[str, dict[str, Any]] = {
    "orders":        {"url": f"http://{'orders' if _docker else 'localhost'}:8001",        "timeout": 5.0, "retries": 2},
    "payments":      {"url": f"http://{'payments' if _docker else 'localhost'}:8002",      "timeout": 5.0, "retries": 2},
    "inventory":     {"url": f"http://{'inventory' if _docker else 'localhost'}:8003",     "timeout": 3.0, "retries": 1},
    "notifications": {"url": f"http://{'notifications' if _docker else 'localhost'}:8004", "timeout": 3.0, "retries": 0},
}

_client: httpx.AsyncClient | None = None
_failure_mode: dict[str, Any] = {"enabled": False, "type": None, "rate": 0.0}
_request_log: list[dict[str, Any]] = []   # rolling window of recent requests
_boot_time: float = time.time()

# Simple per-service failure tracking for gateway-level circuit awareness
_service_failures: dict[str, list[float]] = {s: [] for s in SERVICE_REGISTRY}
FAILURE_WINDOW = 30.0   # seconds
FAILURE_THRESHOLD = 5   # failures within window to trip


async def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0))
    return _client


def _record_failure(service: str) -> None:
    now = time.time()
    _service_failures[service].append(now)
    # Trim old entries
    _service_failures[service] = [t for t in _service_failures[service] if now - t < FAILURE_WINDOW]
    is_open = len(_service_failures[service]) >= FAILURE_THRESHOLD
    GATEWAY_CIRCUIT_OPEN.labels(target=service).set(1 if is_open else 0)


def _is_circuit_open(service: str) -> bool:
    now = time.time()
    _service_failures[service] = [t for t in _service_failures[service] if now - t < FAILURE_WINDOW]
    return len(_service_failures[service]) >= FAILURE_THRESHOLD


def _record_success(service: str) -> None:
    # Clear half the failure history on success (half-open behaviour)
    if _service_failures[service]:
        _service_failures[service] = _service_failures[service][len(_service_failures[service]) // 2:]
    GATEWAY_CIRCUIT_OPEN.labels(target=service).set(0)


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------
async def _call_service(
    service: str,
    method: str,
    path: str,
    *,
    json: dict | None = None,
    headers: dict | None = None,
) -> httpx.Response:
    """Call a downstream service with retry + exponential backoff."""
    reg = SERVICE_REGISTRY[service]
    url = f"{reg['url']}{path}"
    max_retries = reg["retries"]
    timeout = reg["timeout"]
    client = await get_client()

    if _is_circuit_open(service):
        logger.warning("gateway.circuit_open", service=service)
        await get_event_bus().publish(Event(
            category=EventCategory.DETECTION,
            event_type="circuit_open",
            severity=EventSeverity.WARNING,
            source="gateway",
            payload={"service": service, "recent_failures": len(_service_failures[service])},
        ))
        raise httpx.RequestError(f"Circuit open for {service}")

    last_exc: Exception | None = None
    for attempt in range(1 + max_retries):
        try:
            if method == "GET":
                resp = await client.get(url, headers=headers, timeout=timeout)
            else:
                resp = await client.post(url, json=json, headers=headers, timeout=timeout)
            _record_success(service)
            return resp
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            last_exc = exc
            _record_failure(service)
            if attempt < max_retries:
                GATEWAY_RETRIES.labels(target=service).inc()
                backoff = 0.1 * (2 ** attempt) + random.uniform(0, 0.05)
                logger.warning("gateway.retry", service=service, attempt=attempt + 1, backoff=f"{backoff:.2f}s")
                await asyncio.sleep(backoff)

    # All retries exhausted
    await get_event_bus().publish(Event(
        category=EventCategory.DETECTION,
        event_type="dependency_failure",
        severity=EventSeverity.CRITICAL,
        source="gateway",
        payload={"dependency": service, "error": str(last_exc), "retries_exhausted": max_retries},
    ))
    raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
@app.middleware("http")
async def tracing_middleware(request: Request, call_next) -> Response:
    """Inject correlation ID + track request metrics."""
    correlation_id = request.headers.get("X-Correlation-ID", uuid.uuid4().hex[:12])
    request.state.correlation_id = correlation_id

    start = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - start

    route = request.url.path
    GATEWAY_REQUESTS.labels(method=request.method, route=route, status=response.status_code).inc()
    GATEWAY_LATENCY.observe(elapsed)

    response.headers["X-Correlation-ID"] = correlation_id
    response.headers["X-Response-Time"] = f"{elapsed:.4f}"

    # Rolling request log (keep last 200)
    _request_log.append({
        "method": request.method, "path": route,
        "status": response.status_code, "latency": round(elapsed, 4),
        "correlation_id": correlation_id, "timestamp": time.time(),
    })
    if len(_request_log) > 200:
        _request_log.pop(0)

    return response


# ---------------------------------------------------------------------------
# Chaos injection (gateway was missing this!)
# ---------------------------------------------------------------------------
@app.post("/chaos/enable")
async def enable_chaos(request: Request) -> dict[str, Any]:
    global _failure_mode
    body = await request.json()
    _failure_mode = {
        "enabled": True,
        "type": body.get("type", "error"),
        "rate": body.get("rate", 0.5),
        "delay": body.get("delay", 2.0),
    }
    logger.warning("chaos.enabled", mode=_failure_mode)
    return {"status": "chaos_enabled", "mode": _failure_mode}


@app.post("/chaos/disable")
async def disable_chaos() -> dict[str, Any]:
    global _failure_mode
    _failure_mode = {"enabled": False, "type": None, "rate": 0.0}
    logger.info("chaos.disabled")
    return {"status": "chaos_disabled"}


async def _maybe_inject_chaos() -> None:
    if not _failure_mode["enabled"]:
        return
    if random.random() >= _failure_mode.get("rate", 0.5):
        return
    if _failure_mode["type"] == "error":
        raise HTTPException(status_code=500, detail="Gateway injected failure")
    elif _failure_mode["type"] == "latency":
        await asyncio.sleep(_failure_mode.get("delay", 2.0))


# ---------------------------------------------------------------------------
# Service discovery + health
# ---------------------------------------------------------------------------
@app.get("/api/services")
async def list_services() -> dict[str, Any]:
    """Shallow health check — fast, just pings /health on each service."""
    client = await get_client()
    statuses: dict[str, Any] = {}
    for name, reg in SERVICE_REGISTRY.items():
        try:
            resp = await client.get(f"{reg['url']}/health", timeout=3.0)
            statuses[name] = resp.json()
        except Exception:
            statuses[name] = {"service": name, "status": "unreachable"}
    return {"services": statuses}


@app.get("/api/services/deep-health")
async def deep_health() -> dict[str, Any]:
    """Deep health check — pings every service, checks circuit state, aggregates."""
    client = await get_client()
    results: dict[str, Any] = {}
    healthy_count = 0

    for name, reg in SERVICE_REGISTRY.items():
        entry: dict[str, Any] = {
            "service": name,
            "url": reg["url"],
            "timeout": reg["timeout"],
            "retries": reg["retries"],
            "circuit_open": _is_circuit_open(name),
            "recent_failures": len(_service_failures.get(name, [])),
        }
        try:
            start = time.perf_counter()
            resp = await client.get(f"{reg['url']}/health", timeout=reg["timeout"])
            entry["latency_ms"] = round((time.perf_counter() - start) * 1000, 2)
            entry["status"] = "healthy" if resp.status_code == 200 else "degraded"
            entry["health_data"] = resp.json()
            if entry["status"] == "healthy":
                healthy_count += 1
        except Exception as exc:
            entry["status"] = "unreachable"
            entry["error"] = str(exc)
            entry["latency_ms"] = None

        results[name] = entry

    total = len(SERVICE_REGISTRY)
    return {
        "overall": "healthy" if healthy_count == total else ("degraded" if healthy_count > 0 else "down"),
        "healthy": healthy_count,
        "total": total,
        "uptime_seconds": round(time.time() - _boot_time, 1),
        "services": results,
    }


@app.get("/api/gateway/stats")
async def gateway_stats() -> dict[str, Any]:
    """Gateway throughput and error budget stats."""
    recent = _request_log[-100:] if _request_log else []
    total = len(recent)
    errors = sum(1 for r in recent if r["status"] >= 500)
    avg_latency = sum(r["latency"] for r in recent) / max(total, 1)
    p99_latency = sorted(r["latency"] for r in recent)[int(total * 0.99)] if total > 1 else 0

    return {
        "uptime_seconds": round(time.time() - _boot_time, 1),
        "recent_requests": total,
        "error_count": errors,
        "error_rate": round(errors / max(total, 1), 4),
        "avg_latency_ms": round(avg_latency * 1000, 2),
        "p99_latency_ms": round(p99_latency * 1000, 2),
        "circuit_states": {
            name: {"open": _is_circuit_open(name), "failures": len(fails)}
            for name, fails in _service_failures.items()
        },
        "chaos_mode": _failure_mode,
    }


@app.get("/api/gateway/requests")
async def recent_requests(limit: int = 50) -> dict[str, Any]:
    """Return the last N requests routed through the gateway."""
    return {"requests": _request_log[-limit:], "total_logged": len(_request_log)}


# ---------------------------------------------------------------------------
# Order pipeline
# ---------------------------------------------------------------------------
@app.post("/api/orders")
async def create_order(request: Request) -> dict[str, Any]:
    """Route order creation through the full pipeline:
    inventory check -> order create -> payment -> notification."""
    await _maybe_inject_chaos()

    body = await request.json()
    correlation_id = getattr(request.state, "correlation_id", uuid.uuid4().hex[:12])
    headers = {"X-Correlation-ID": correlation_id}
    pipeline_start = time.perf_counter()
    steps: list[dict[str, Any]] = []

    # Step 1: Check inventory
    step_start = time.perf_counter()
    try:
        inv_resp = await _call_service(
            "inventory", "POST", "/inventory/check",
            json={"items": body.get("items", [])}, headers=headers,
        )
        if inv_resp.status_code != 200:
            raise HTTPException(status_code=422, detail="Inventory check failed")
        steps.append({"step": "inventory_check", "status": "ok", "latency_ms": round((time.perf_counter() - step_start) * 1000, 2)})
    except httpx.RequestError as e:
        logger.error("gateway.inventory_unreachable", error=str(e))
        raise HTTPException(status_code=503, detail="Inventory service unavailable")

    # Step 2: Create order
    step_start = time.perf_counter()
    try:
        order_resp = await _call_service(
            "orders", "POST", "/orders",
            json=body, headers=headers,
        )
        order_data = order_resp.json()
        steps.append({"step": "order_create", "status": "ok", "latency_ms": round((time.perf_counter() - step_start) * 1000, 2)})
    except httpx.RequestError as e:
        logger.error("gateway.orders_unreachable", error=str(e))
        raise HTTPException(status_code=503, detail="Order service unavailable")

    # Step 3: Process payment
    step_start = time.perf_counter()
    try:
        pay_resp = await _call_service(
            "payments", "POST", "/payments",
            json={
                "order_id": order_data.get("order_id"),
                "amount": body.get("total", 0),
                "method": body.get("payment_method", "card"),
            },
            headers=headers,
        )
        payment_data = pay_resp.json()
        steps.append({"step": "payment", "status": "ok", "latency_ms": round((time.perf_counter() - step_start) * 1000, 2)})
    except (httpx.RequestError, HTTPException) as e:
        logger.error("gateway.payments_unreachable", error=str(e))
        raise HTTPException(status_code=503, detail="Payment service unavailable")

    # Step 4: Notification (fire-and-forget — non-critical)
    step_start = time.perf_counter()
    try:
        await _call_service(
            "notifications", "POST", "/notifications",
            json={
                "order_id": order_data.get("order_id"),
                "type": "order_confirmation",
                "channel": "email",
                "recipient": body.get("customer_email", ""),
            },
            headers=headers,
        )
        steps.append({"step": "notification", "status": "ok", "latency_ms": round((time.perf_counter() - step_start) * 1000, 2)})
    except Exception:
        steps.append({"step": "notification", "status": "skipped", "latency_ms": round((time.perf_counter() - step_start) * 1000, 2)})
        logger.warning("gateway.notification_failed", order_id=order_data.get("order_id"))

    total_ms = round((time.perf_counter() - pipeline_start) * 1000, 2)

    return {
        "correlation_id": correlation_id,
        "order": order_data,
        "payment": payment_data,
        "status": "completed",
        "pipeline": {"total_ms": total_ms, "steps": steps},
    }


@app.get("/api/orders/{order_id}")
async def get_order(order_id: str, request: Request) -> dict[str, Any]:
    correlation_id = getattr(request.state, "correlation_id", "")
    try:
        resp = await _call_service(
            "orders", "GET", f"/orders/{order_id}",
            headers={"X-Correlation-ID": correlation_id},
        )
        return resp.json()
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Order service unavailable")


@app.get("/api/orders")
async def list_orders(request: Request, limit: int = 50) -> dict[str, Any]:
    correlation_id = getattr(request.state, "correlation_id", "")
    try:
        resp = await _call_service(
            "orders", "GET", f"/orders?limit={limit}",
            headers={"X-Correlation-ID": correlation_id},
        )
        return resp.json()
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Order service unavailable")


# ---------------------------------------------------------------------------
# Proxy endpoints for individual services
# ---------------------------------------------------------------------------
@app.get("/api/inventory/stock")
async def proxy_inventory_stock(request: Request) -> dict[str, Any]:
    try:
        resp = await _call_service("inventory", "GET", "/inventory/stock")
        return resp.json()
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Inventory service unavailable")


@app.get("/api/payments/{payment_id}")
async def proxy_get_payment(payment_id: str, request: Request) -> dict[str, Any]:
    try:
        resp = await _call_service("payments", "GET", f"/payments/{payment_id}")
        return resp.json()
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Payment service unavailable")


@app.get("/api/payments/providers/health")
async def proxy_provider_health() -> dict[str, Any]:
    try:
        resp = await _call_service("payments", "GET", "/payments/providers/health")
        return resp.json()
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Payment service unavailable")
