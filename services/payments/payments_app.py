"""
✒ Metadata
    - Title: Payment Service (AREF Edition - v2.0)
    - File Name: payments_app.py
    - Relative Path: services/payments/payments_app.py
    - Artifact Type: script
    - Version: 2.0.0
    - Date: 2026-03-13
    - Update: Thursday, March 13, 2026
    - Author: Dennis 'dnoice' Smaltz
    - A.I. Acknowledgement: Anthropic - Claude Opus 4
    - Signature: ︻デ═─── ✦ ✦ ✦ | Aim Twice, Shoot Once!
 
✒ Description:
    Simulated payment processing microservice with a multi-provider ecosystem
    (Stripe, Square, PayPal), automatic failover after consecutive failures,
    full and partial refund support, batch settlement simulation, and AREF
    event bus integration. Designed as the primary circuit-breaker and
    dependency-substitution demonstration target within the AREF platform.
 
✒ Key Features:
    - Feature 1: Multi-provider ecosystem — Stripe, Square, and PayPal with
                  distinct latency profiles (100ms, 150ms, 200ms base) and
                  failure rates (1%, 2%, 3%) simulating real-world variance
    - Feature 2: Auto-failover — after 3 consecutive failures on the active
                  provider, automatically switches to the next healthy provider
                  in the failover chain with event bus logging and switch history
    - Feature 3: Provider simulation — realistic async latency with jitter,
                  configurable failure injection (error, latency, timeout modes),
                  and per-provider health tracking via Prometheus gauges
    - Feature 4: Payment lifecycle — pending → approved → settled → refunded
                  with full audit trail per payment including correlation ID,
                  provider, transaction ID, and timestamps
    - Feature 5: Full and partial refund support — POST /payments/{id}/refund
                  with amount override (defaults to full), reason tracking, and
                  event bus publication
    - Feature 6: Batch settlement simulation — POST /payments/settle processes
                  all approved-but-unsettled payments with simulated latency
    - Feature 7: Manual provider switching — POST /payments/provider for the
                  Adaptation pillar to force provider changes
    - Feature 8: Provider health dashboard — GET /payments/providers/health
                  showing active provider, health scores, failure rates, latency
                  baselines, consecutive failures, and switch log
    - Feature 9: Provider reset — POST /payments/providers/reset restores all
                  providers to full health and resets to Stripe primary
    - Feature 10: Prometheus metrics — payments_processed_total (by status and
                   provider), payments_latency_seconds histogram, provider health
                   gauges, refund counter, pending settlement gauge
    - Feature 11: Aggregate statistics — total payments, by status, by provider,
                   total volume, average amount, average latency, refund count
    - Feature 12: Chaos injection — error, latency, and timeout fault modes;
                   timeout mode simulates a 15-second provider hang
 
✒ Usage Instructions:
    Start via uvicorn:
        $ uvicorn services.payments.payments_app:app --host 0.0.0.0 --port 8002
 
    Or via Docker Compose as part of the AREF microservice stack.
 
✒ Examples:
    # Process payment
    $ curl -X POST http://localhost:8002/payments \
        -d '{"order_id":"ORD-123","amount":49.99,"method":"card"}'
 
    # Full refund
    $ curl -X POST http://localhost:8002/payments/PAY-ABCD1234/refund \
        -d '{"reason":"customer_request"}'
 
    # Partial refund
    $ curl -X POST http://localhost:8002/payments/PAY-ABCD1234/refund \
        -d '{"amount":10.00,"reason":"partial_return"}'
 
    # Batch settle
    $ curl -X POST http://localhost:8002/payments/settle
 
    # Switch provider
    $ curl -X POST http://localhost:8002/payments/provider \
        -d '{"provider":"square"}'
 
    # Provider health
    $ curl http://localhost:8002/payments/providers/health
 
    # Reset providers
    $ curl -X POST http://localhost:8002/payments/providers/reset
 
    # Statistics
    $ curl http://localhost:8002/payments/stats/summary
 
    # Enable chaos (timeout)
    $ curl -X POST http://localhost:8002/chaos/enable \
        -d '{"type":"timeout","rate":0.5}'
 
✒ Other Important Information:
    - Dependencies:
        Required: fastapi, structlog, prometheus_client
        Internal: services.base, aref.core.events
    - Compatible platforms: Linux, macOS, Docker (Python 3.11+)
    - Performance notes: Provider simulation uses asyncio.sleep; settlement is
      sequential; in-memory storage for all records
    - Security considerations: No authentication; provider switch endpoint is
      unauthenticated; no amount validation
    - Known limitations: In-memory only; linear failover (no weighted selection);
      no idempotency keys; chaos timeout (15s) triggers upstream gateway timeouts
---------
"""

from __future__ import annotations

import asyncio
import random
import time
import uuid
from typing import Any

import structlog
from fastapi import HTTPException, Request
from prometheus_client import Counter, Gauge, Histogram

from services.base import create_service
from aref.core.events import Event, EventCategory, EventSeverity, get_event_bus

logger = structlog.get_logger(__name__)

app = create_service(
    name="payments",
    description="Payment processing with multi-provider failover, refunds, and settlement",
)

# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
PAYMENT_PROCESSED = Counter("payments_processed_total", "Payments processed", ["status", "provider"])
PAYMENT_LATENCY = Histogram(
    "payments_latency_seconds", "Payment processing latency",
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)
PROVIDER_HEALTH = Gauge("payments_provider_health", "Provider health score", ["provider"])
REFUND_COUNTER = Counter("payments_refunds_total", "Refunds processed", ["status", "type"])
SETTLEMENT_GAUGE = Gauge("payments_pending_settlement", "Payments pending settlement")

# ---------------------------------------------------------------------------
# Provider ecosystem
# ---------------------------------------------------------------------------
PROVIDERS: dict[str, dict[str, Any]] = {
    "stripe":  {"latency_base": 0.1,  "failure_rate": 0.01, "health": 1.0, "consecutive_failures": 0},
    "square":  {"latency_base": 0.15, "failure_rate": 0.02, "health": 1.0, "consecutive_failures": 0},
    "paypal":  {"latency_base": 0.2,  "failure_rate": 0.03, "health": 1.0, "consecutive_failures": 0},
}
PROVIDER_ORDER = ["stripe", "square", "paypal"]  # failover priority
_active_provider = "stripe"
AUTO_FAILOVER_THRESHOLD = 3  # consecutive failures before auto-switch

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
_payments: dict[str, dict[str, Any]] = {}
_refunds: dict[str, dict[str, Any]] = {}
_failure_mode: dict[str, Any] = {"enabled": False, "type": None, "rate": 0.0}
_provider_switch_log: list[dict[str, Any]] = []


def _next_provider(current: str) -> str | None:
    """Return next provider in failover chain, or None if exhausted."""
    idx = PROVIDER_ORDER.index(current) if current in PROVIDER_ORDER else -1
    for i in range(idx + 1, len(PROVIDER_ORDER)):
        candidate = PROVIDER_ORDER[i]
        if PROVIDERS[candidate]["health"] > 0:
            return candidate
    return None


def _auto_failover(failed_provider: str) -> str | None:
    """Check if we should auto-failover and do it."""
    global _active_provider
    cfg = PROVIDERS[failed_provider]
    cfg["consecutive_failures"] += 1

    if cfg["consecutive_failures"] >= AUTO_FAILOVER_THRESHOLD:
        cfg["health"] = 0.0
        PROVIDER_HEALTH.labels(provider=failed_provider).set(0.0)
        next_prov = _next_provider(failed_provider)
        if next_prov:
            old = _active_provider
            _active_provider = next_prov
            _provider_switch_log.append({
                "from": old, "to": next_prov,
                "reason": "auto_failover",
                "timestamp": time.time(),
            })
            logger.warning("payment.auto_failover", old=old, new=next_prov,
                           consecutive_failures=cfg["consecutive_failures"])
            return next_prov
    return None


# ---------------------------------------------------------------------------
# Provider simulation
# ---------------------------------------------------------------------------
async def simulate_provider(provider: str, amount: float) -> dict[str, Any]:
    """Simulate a payment provider call with realistic latency and failure characteristics."""
    config = PROVIDERS.get(provider, PROVIDERS["stripe"])

    # Chaos injection
    if _failure_mode["enabled"]:
        if random.random() < _failure_mode.get("rate", 0.5):
            if _failure_mode["type"] == "error":
                raise Exception(f"Provider {provider} injected failure")
            elif _failure_mode["type"] == "latency":
                await asyncio.sleep(_failure_mode.get("delay", 3.0))
            elif _failure_mode["type"] == "timeout":
                await asyncio.sleep(15.0)

    # Normal simulation
    latency = config["latency_base"] + random.uniform(0, 0.1)
    await asyncio.sleep(latency)

    if random.random() < config["failure_rate"]:
        raise Exception(f"Provider {provider} declined transaction")

    return {
        "provider": provider,
        "transaction_id": f"TXN-{uuid.uuid4().hex[:10].upper()}",
        "amount": amount,
        "status": "approved",
        "latency_ms": round(latency * 1000, 2),
    }


# ---------------------------------------------------------------------------
# Payment processing
# ---------------------------------------------------------------------------
@app.post("/payments")
async def process_payment(request: Request) -> dict[str, Any]:
    start = time.perf_counter()
    body = await request.json()
    amount = body.get("amount", 0)
    order_id = body.get("order_id", "unknown")
    method = body.get("method", "card")
    correlation_id = request.headers.get("X-Correlation-ID", "")

    provider_used = _active_provider
    try:
        result = await simulate_provider(provider_used, amount)
        payment_id = f"PAY-{uuid.uuid4().hex[:8].upper()}"
        now = time.time()
        payment = {
            "payment_id": payment_id,
            "order_id": order_id,
            "method": method,
            **result,
            "settled": False,
            "created_at": now,
            "updated_at": now,
            "correlation_id": correlation_id,
        }
        _payments[payment_id] = payment

        elapsed = time.perf_counter() - start
        PAYMENT_PROCESSED.labels(status="success", provider=provider_used).inc()
        PAYMENT_LATENCY.observe(elapsed)
        PROVIDER_HEALTH.labels(provider=provider_used).set(1.0)
        PROVIDERS[provider_used]["consecutive_failures"] = 0
        PROVIDERS[provider_used]["health"] = 1.0
        SETTLEMENT_GAUGE.set(sum(1 for p in _payments.values() if not p.get("settled")))

        logger.info("payment.processed", payment_id=payment_id, provider=provider_used)

        await get_event_bus().publish(Event(
            category=EventCategory.SYSTEM,
            event_type="payment_processed",
            source="payments",
            payload={"payment_id": payment_id, "amount": amount, "provider": provider_used},
            correlation_id=correlation_id,
        ))

        return payment

    except Exception as e:
        elapsed = time.perf_counter() - start
        PAYMENT_PROCESSED.labels(status="failed", provider=provider_used).inc()
        PAYMENT_LATENCY.observe(elapsed)
        PROVIDER_HEALTH.labels(provider=provider_used).set(0.0)

        # Try auto-failover
        new_prov = _auto_failover(provider_used)

        await get_event_bus().publish(Event(
            category=EventCategory.DETECTION,
            event_type="payment_failure",
            severity=EventSeverity.WARNING,
            source="payments",
            payload={
                "provider": provider_used, "error": str(e),
                "failover_to": new_prov, "order_id": order_id,
            },
            correlation_id=correlation_id,
        ))

        logger.error("payment.failed", error=str(e), provider=provider_used, failover=new_prov)
        raise HTTPException(status_code=502, detail=f"Payment processing failed: {e}")


@app.get("/payments/{payment_id}")
async def get_payment(payment_id: str) -> dict[str, Any]:
    if payment_id not in _payments:
        raise HTTPException(status_code=404, detail="Payment not found")
    return _payments[payment_id]


@app.get("/payments")
async def list_payments(limit: int = 50, status: str | None = None) -> dict[str, Any]:
    payments = list(_payments.values())
    if status:
        payments = [p for p in payments if p.get("status") == status]
    return {"payments": payments[-limit:], "total": len(_payments)}


# ---------------------------------------------------------------------------
# Refunds
# ---------------------------------------------------------------------------
@app.post("/payments/{payment_id}/refund")
async def refund_payment(payment_id: str, request: Request) -> dict[str, Any]:
    """Process a full or partial refund."""
    if payment_id not in _payments:
        raise HTTPException(status_code=404, detail="Payment not found")

    payment = _payments[payment_id]
    if payment["status"] == "refunded":
        raise HTTPException(status_code=422, detail="Payment already refunded")

    body = await request.json()
    refund_amount = body.get("amount", payment["amount"])  # default to full refund
    reason = body.get("reason", "customer_request")
    refund_type = "full" if refund_amount >= payment["amount"] else "partial"

    await asyncio.sleep(random.uniform(0.05, 0.15))  # simulate processing

    refund_id = f"RFD-{uuid.uuid4().hex[:8].upper()}"
    now = time.time()
    refund = {
        "refund_id": refund_id,
        "payment_id": payment_id,
        "order_id": payment["order_id"],
        "original_amount": payment["amount"],
        "refund_amount": refund_amount,
        "refund_type": refund_type,
        "reason": reason,
        "provider": payment["provider"],
        "status": "processed",
        "created_at": now,
    }
    _refunds[refund_id] = refund

    payment["status"] = "refunded"
    payment["refund_id"] = refund_id
    payment["updated_at"] = now

    REFUND_COUNTER.labels(status="success", type=refund_type).inc()

    await get_event_bus().publish(Event(
        category=EventCategory.SYSTEM,
        event_type="payment_refunded",
        severity=EventSeverity.INFO,
        source="payments",
        payload={"refund_id": refund_id, "payment_id": payment_id, "amount": refund_amount},
    ))

    logger.info("payment.refunded", refund_id=refund_id, payment_id=payment_id, amount=refund_amount)
    return refund


@app.get("/payments/refunds/list")
async def list_refunds(limit: int = 50) -> dict[str, Any]:
    return {"refunds": list(_refunds.values())[-limit:], "total": len(_refunds)}


# ---------------------------------------------------------------------------
# Settlement simulation
# ---------------------------------------------------------------------------
@app.post("/payments/settle")
async def settle_payments() -> dict[str, Any]:
    """Simulate batch settlement of approved payments."""
    settled = []
    now = time.time()
    for pid, payment in _payments.items():
        if payment["status"] == "approved" and not payment.get("settled"):
            await asyncio.sleep(random.uniform(0.01, 0.03))  # simulate
            payment["settled"] = True
            payment["settled_at"] = now
            payment["status"] = "settled"
            payment["updated_at"] = now
            settled.append(pid)

    SETTLEMENT_GAUGE.set(sum(1 for p in _payments.values() if not p.get("settled")))
    logger.info("payments.settled", count=len(settled))
    return {"settled": len(settled), "payment_ids": settled}


# ---------------------------------------------------------------------------
# Provider management
# ---------------------------------------------------------------------------
@app.post("/payments/provider")
async def switch_provider(request: Request) -> dict[str, Any]:
    """Switch active payment provider (used by Adaptation pillar)."""
    global _active_provider
    body = await request.json()
    new_provider = body.get("provider", "stripe")
    if new_provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {new_provider}")
    old = _active_provider
    _active_provider = new_provider
    _provider_switch_log.append({
        "from": old, "to": new_provider,
        "reason": "manual",
        "timestamp": time.time(),
    })
    logger.info("payment.provider_switched", old=old, new=new_provider)
    return {"old_provider": old, "new_provider": new_provider}


@app.get("/payments/providers/health")
async def provider_health() -> dict[str, Any]:
    return {
        "active": _active_provider,
        "failover_threshold": AUTO_FAILOVER_THRESHOLD,
        "providers": {
            name: {
                "health": cfg["health"],
                "failure_rate": cfg["failure_rate"],
                "latency_base_ms": round(cfg["latency_base"] * 1000),
                "consecutive_failures": cfg["consecutive_failures"],
            }
            for name, cfg in PROVIDERS.items()
        },
        "switch_history": _provider_switch_log[-20:],
    }


@app.post("/payments/providers/reset")
async def reset_providers() -> dict[str, Any]:
    """Reset all provider health (recovery after incident)."""
    global _active_provider
    for name, cfg in PROVIDERS.items():
        cfg["health"] = 1.0
        cfg["consecutive_failures"] = 0
        PROVIDER_HEALTH.labels(provider=name).set(1.0)
    _active_provider = "stripe"
    logger.info("payments.providers_reset")
    return {"status": "all_providers_reset", "active": _active_provider}


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------
@app.get("/payments/stats/summary")
async def payment_stats() -> dict[str, Any]:
    if not _payments:
        return {"total": 0, "by_status": {}, "by_provider": {}, "total_volume": 0}

    by_status: dict[str, int] = {}
    by_provider: dict[str, int] = {}
    total_volume = 0.0
    latencies: list[float] = []

    for p in _payments.values():
        by_status[p["status"]] = by_status.get(p["status"], 0) + 1
        prov = p.get("provider", "unknown")
        by_provider[prov] = by_provider.get(prov, 0) + 1
        total_volume += p.get("amount", 0)
        if "latency_ms" in p:
            latencies.append(p["latency_ms"])

    return {
        "total": len(_payments),
        "by_status": by_status,
        "by_provider": by_provider,
        "total_volume": round(total_volume, 2),
        "avg_amount": round(total_volume / max(len(_payments), 1), 2),
        "avg_latency_ms": round(sum(latencies) / max(len(latencies), 1), 2) if latencies else 0,
        "refunds": len(_refunds),
        "pending_settlement": sum(1 for p in _payments.values() if not p.get("settled")),
    }


# ---------------------------------------------------------------------------
# Chaos endpoints
# ---------------------------------------------------------------------------
@app.post("/chaos/enable")
async def enable_chaos(request: Request) -> dict[str, Any]:
    global _failure_mode
    body = await request.json()
    _failure_mode = {
        "enabled": True,
        "type": body.get("type", "error"),
        "rate": body.get("rate", 0.5),
        "delay": body.get("delay", 3.0),
    }
    return {"status": "chaos_enabled", "mode": _failure_mode}


@app.post("/chaos/disable")
async def disable_chaos() -> dict[str, Any]:
    global _failure_mode
    _failure_mode = {"enabled": False, "type": None, "rate": 0.0}
    return {"status": "chaos_disabled"}
