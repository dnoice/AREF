"""
✒ Metadata
    - Title: Order Service (AREF Edition - v2.0)
    - File Name: orders_app.py
    - Relative Path: services/orders/orders_app.py
    - Artifact Type: script
    - Version: 2.0.0
    - Date: 2026-03-13
    - Update: Thursday, March 13, 2026
    - Author: Dennis 'dnoice' Smaltz
    - A.I. Acknowledgement: Anthropic - Claude Opus 4
    - Signature: ︻デ═─── ✦ ✦ ✦ | Aim Twice, Shoot Once!
 
✒ Description:
    Full order lifecycle management microservice with a strict state machine,
    audit trail, cancellation validation, and AREF event bus instrumentation.
    Built on the shared service factory (services.base.create_service) with
    Prometheus metrics for creation latency, status transitions, and active
    order tracking.
 
✒ Key Features:
    - Feature 1: Six-state order lifecycle — created → confirmed → processing →
                  shipped → delivered (terminal) / cancelled (terminal) — with
                  explicitly defined valid transitions and guard validation
    - Feature 2: Order creation with full payload (items, total, currency,
                  payment method, customer email) and correlation ID propagation
    - Feature 3: Generic status transition endpoint (PATCH /orders/{id}/status)
                  with state machine validation and descriptive 422 errors
    - Feature 4: Convenience shortcuts — POST /orders/{id}/confirm and
                  POST /orders/{id}/cancel with reason tracking
    - Feature 5: Cancellation logic — only allowed in cancellable states
                  (created, confirmed, processing); records reason, publishes
                  WARNING-severity event to the AREF event bus
    - Feature 6: Full audit trail — every lifecycle event logged to a bounded
                  in-memory audit log (5000 entries max) with correlation ID,
                  timestamp, and action detail
    - Feature 7: Order history embedded per-order — each order carries its own
                  status transition history with timestamps and notes
    - Feature 8: Search and filter — list orders with optional status filter,
                  creation time threshold (since), and limit
    - Feature 9: Aggregate statistics — total/active counts, revenue, average
                  order value, lifecycle duration, and cancellation rate
    - Feature 10: Prometheus metrics — orders_created_total (by status),
                   orders_creation_latency_seconds histogram, status transition
                   counter, cancellation counter (by reason), active orders gauge
    - Feature 11: Chaos injection — error or latency fault modes with configurable
                   rate and delay for AREF chaos experiments
    - Feature 12: Event bus integration — publishes order_created and
                   order_cancelled events for downstream pillar consumption
 
✒ Usage Instructions:
    Start via uvicorn:
        $ uvicorn services.orders.orders_app:app --host 0.0.0.0 --port 8001
 
    Or via Docker Compose as part of the AREF microservice stack.
 
✒ Examples:
    # Create order
    $ curl -X POST http://localhost:8001/orders \
        -d '{"items":[{"sku":"WIDGET-001","quantity":2}],"total":19.98}'
 
    # Confirm
    $ curl -X POST http://localhost:8001/orders/ORD-ABCD1234/confirm
 
    # Cancel
    $ curl -X POST http://localhost:8001/orders/ORD-ABCD1234/cancel \
        -d '{"reason":"customer_request"}'
 
    # List by status
    $ curl http://localhost:8001/orders?status=created&limit=10
 
    # Audit log
    $ curl http://localhost:8001/orders/audit/log?limit=50
 
    # Statistics
    $ curl http://localhost:8001/orders/stats/summary
 
✒ Other Important Information:
    - Dependencies:
        Required: fastapi, structlog, prometheus_client
        Internal: services.base, aref.core.events
    - Compatible platforms: Linux, macOS, Docker (Python 3.11+)
    - Performance notes: In-memory storage; audit log bounded at 5000 entries
    - Security considerations: No authentication; no input validation beyond
      JSON parsing; audit log is ephemeral
    - Known limitations: In-memory only; no pagination cursor; chaos is global
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

from services.base import create_service, maybe_inject_chaos
from services.state import InMemoryStore, BoundedLog
from aref.core.events import Event, EventCategory, EventSeverity, get_event_bus

logger = structlog.get_logger(__name__)

app = create_service(
    name="orders",
    description="Order lifecycle management with state machine, audit trail, and SLI instrumentation",
)

# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
ORDER_CREATED = Counter("orders_created_total", "Orders created", ["status"])
ORDER_LATENCY = Histogram(
    "orders_creation_latency_seconds", "Order creation latency",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
)
ORDER_STATUS_TRANSITIONS = Counter(
    "orders_status_transitions_total", "Order status transitions",
    ["from_status", "to_status"],
)
ORDER_CANCELLATIONS = Counter("orders_cancellations_total", "Orders cancelled", ["reason"])
ACTIVE_ORDERS = Gauge("orders_active_count", "Currently active (non-terminal) orders")

# ---------------------------------------------------------------------------
# State machine definition
# ---------------------------------------------------------------------------
VALID_TRANSITIONS: dict[str, list[str]] = {
    "created":    ["confirmed", "cancelled"],
    "confirmed":  ["processing", "cancelled"],
    "processing": ["shipped", "cancelled"],
    "shipped":    ["delivered"],
    "delivered":  [],       # terminal
    "cancelled":  [],       # terminal
}
TERMINAL_STATES = {"delivered", "cancelled"}
CANCELLABLE_STATES = {"created", "confirmed", "processing"}

# ---------------------------------------------------------------------------
# In-memory stores
# ---------------------------------------------------------------------------
_orders: InMemoryStore[dict[str, Any]] = InMemoryStore(max_entries=10_000)
_audit_log: BoundedLog[dict[str, Any]] = BoundedLog(max_entries=5000)


def _audit(order_id: str, action: str, detail: str = "", correlation_id: str = "") -> dict[str, Any]:
    entry = {
        "order_id": order_id,
        "action": action,
        "detail": detail,
        "correlation_id": correlation_id,
        "timestamp": time.time(),
    }
    _audit_log.append(entry)
    return entry


def _count_active() -> int:
    return sum(1 for o in _orders.values() if o["status"] not in TERMINAL_STATES)


# ---------------------------------------------------------------------------
# Order CRUD
# ---------------------------------------------------------------------------
@app.post("/orders")
async def create_order(request: Request) -> dict[str, Any]:
    start = time.perf_counter()
    await maybe_inject_chaos(request.app, detail="Injected order failure")

    body = await request.json()
    correlation_id = request.headers.get("X-Correlation-ID", "")

    order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
    now = time.time()
    items = body.get("items", [])
    total = body.get("total", 0)

    order = {
        "order_id": order_id,
        "customer_email": body.get("customer_email", ""),
        "items": items,
        "item_count": len(items),
        "total": total,
        "currency": body.get("currency", "USD"),
        "status": "created",
        "payment_method": body.get("payment_method", "card"),
        "created_at": now,
        "updated_at": now,
        "correlation_id": correlation_id,
        "history": [{"status": "created", "timestamp": now, "note": "Order placed"}],
    }
    _orders[order_id] = order
    ACTIVE_ORDERS.set(_count_active())

    elapsed = time.perf_counter() - start
    ORDER_LATENCY.observe(elapsed)
    ORDER_CREATED.labels(status="success").inc()
    _audit(order_id, "created", f"total={total}, items={len(items)}", correlation_id)

    # Publish event
    await get_event_bus().publish(Event(
        category=EventCategory.SYSTEM,
        event_type="order_created",
        source="orders",
        payload={"order_id": order_id, "total": total, "items": len(items)},
        correlation_id=correlation_id,
    ))

    logger.info("order.created", order_id=order_id, elapsed=f"{elapsed:.4f}s")
    return order


@app.get("/orders/{order_id}")
async def get_order(order_id: str) -> dict[str, Any]:
    if order_id not in _orders:
        raise HTTPException(status_code=404, detail="Order not found")
    return _orders[order_id]


@app.get("/orders")
async def list_orders(
    limit: int = 50,
    status: str | None = None,
    since: float | None = None,
) -> dict[str, Any]:
    """List orders with optional filtering by status and creation time."""
    orders = list(_orders.values())

    if status:
        orders = [o for o in orders if o["status"] == status]
    if since:
        orders = [o for o in orders if o["created_at"] >= since]

    orders = orders[-limit:]

    return {
        "orders": orders,
        "count": len(orders),
        "total": len(_orders),
        "filters": {"status": status, "since": since, "limit": limit},
    }


# ---------------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------------
@app.patch("/orders/{order_id}/status")
async def update_order_status(order_id: str, request: Request) -> dict[str, Any]:
    if order_id not in _orders:
        raise HTTPException(status_code=404, detail="Order not found")

    body = await request.json()
    new_status = body.get("status", "")
    note = body.get("note", "")
    order = _orders[order_id]
    current = order["status"]

    if new_status not in VALID_TRANSITIONS.get(current, []):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid transition: {current} -> {new_status}. "
                   f"Allowed: {VALID_TRANSITIONS.get(current, [])}",
        )

    now = time.time()
    order["status"] = new_status
    order["updated_at"] = now
    order["history"].append({
        "status": new_status,
        "timestamp": now,
        "note": note or f"Transitioned from {current}",
    })

    ORDER_STATUS_TRANSITIONS.labels(from_status=current, to_status=new_status).inc()
    ACTIVE_ORDERS.set(_count_active())

    _audit(order_id, "status_change", f"{current} -> {new_status}", order.get("correlation_id", ""))

    logger.info("order.status_changed", order_id=order_id, old=current, new=new_status)
    return order


@app.post("/orders/{order_id}/confirm")
async def confirm_order(order_id: str) -> dict[str, Any]:
    """Shortcut to confirm a created order."""
    if order_id not in _orders:
        raise HTTPException(status_code=404, detail="Order not found")
    order = _orders[order_id]
    if order["status"] != "created":
        raise HTTPException(status_code=422, detail=f"Cannot confirm order in '{order['status']}' state")

    now = time.time()
    order["status"] = "confirmed"
    order["updated_at"] = now
    order["confirmed_at"] = now
    order["history"].append({"status": "confirmed", "timestamp": now, "note": "Order confirmed"})
    ORDER_STATUS_TRANSITIONS.labels(from_status="created", to_status="confirmed").inc()
    ACTIVE_ORDERS.set(_count_active())
    _audit(order_id, "confirmed", "", order.get("correlation_id", ""))
    return order


@app.post("/orders/{order_id}/cancel")
async def cancel_order(order_id: str, request: Request) -> dict[str, Any]:
    """Cancel an order — only allowed before delivery."""
    if order_id not in _orders:
        raise HTTPException(status_code=404, detail="Order not found")

    body = await request.json()
    reason = body.get("reason", "customer_request")
    order = _orders[order_id]

    if order["status"] not in CANCELLABLE_STATES:
        raise HTTPException(
            status_code=422,
            detail=f"Cannot cancel order in '{order['status']}' state. "
                   f"Cancellable states: {sorted(CANCELLABLE_STATES)}",
        )

    now = time.time()
    old_status = order["status"]
    order["status"] = "cancelled"
    order["updated_at"] = now
    order["cancelled_at"] = now
    order["cancellation_reason"] = reason
    order["history"].append({
        "status": "cancelled", "timestamp": now,
        "note": f"Cancelled from {old_status}: {reason}",
    })

    ORDER_STATUS_TRANSITIONS.labels(from_status=old_status, to_status="cancelled").inc()
    ORDER_CANCELLATIONS.labels(reason=reason).inc()
    ACTIVE_ORDERS.set(_count_active())

    _audit(order_id, "cancelled", f"reason={reason}, was={old_status}", order.get("correlation_id", ""))

    await get_event_bus().publish(Event(
        category=EventCategory.SYSTEM,
        event_type="order_cancelled",
        severity=EventSeverity.WARNING,
        source="orders",
        payload={"order_id": order_id, "reason": reason, "previous_status": old_status},
    ))

    logger.info("order.cancelled", order_id=order_id, reason=reason)
    return order


# ---------------------------------------------------------------------------
# Audit + Statistics
# ---------------------------------------------------------------------------
@app.get("/orders/audit/log")
async def get_audit_log(limit: int = 100, order_id: str | None = None) -> dict[str, Any]:
    entries = _audit_log
    if order_id:
        entries = [e for e in entries if e["order_id"] == order_id]
    return {"entries": entries[-limit:], "total": len(entries)}


@app.get("/orders/stats/summary")
async def order_stats() -> dict[str, Any]:
    """Aggregate order statistics."""
    if not _orders:
        return {"total": 0, "by_status": {}, "revenue": 0, "avg_order_value": 0}

    by_status: dict[str, int] = {}
    total_revenue = 0.0
    latencies: list[float] = []

    for o in _orders.values():
        st = o["status"]
        by_status[st] = by_status.get(st, 0) + 1
        total_revenue += o.get("total", 0)
        if len(o.get("history", [])) >= 2:
            created = o["history"][0]["timestamp"]
            last = o["history"][-1]["timestamp"]
            latencies.append(last - created)

    total = len(_orders)
    return {
        "total": total,
        "active": _count_active(),
        "by_status": by_status,
        "revenue": round(total_revenue, 2),
        "avg_order_value": round(total_revenue / max(total, 1), 2),
        "avg_lifecycle_seconds": round(sum(latencies) / max(len(latencies), 1), 2) if latencies else 0,
        "cancellation_rate": round(by_status.get("cancelled", 0) / max(total, 1), 4),
    }
