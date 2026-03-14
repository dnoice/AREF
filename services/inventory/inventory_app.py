"""
✒ Metadata
    - Title: Inventory Service (AREF Edition - v2.0)
    - File Name: inventory_app.py
    - Relative Path: services/inventory/inventory_app.py
    - Artifact Type: script
    - Version: 2.0.0
    - Date: 2026-03-13
    - Update: Thursday, March 13, 2026
    - Author: Dennis 'dnoice' Smaltz
    - A.I. Acknowledgement: Anthropic - Claude Opus 4
    - Signature: ︻デ═─── ✦ ✦ ✦ | Aim Twice, Shoot Once!
 
✒ Description:
    Stock management microservice demonstrating AREF graceful degradation tiers
    in action. Manages a product catalog with stock levels, reservations with
    automatic TTL expiry, replenishment simulation, low-stock alerting via the
    AREF event bus, and three-tier degradation (full → degraded → minimal)
    that progressively reduces functionality under stress.
 
✒ Key Features:
    - Feature 1: Three-tier graceful degradation — FULL (complete inventory data
                  with pricing), DEGRADED (stock availability without pricing),
                  MINIMAL (static cached responses only) — switchable via the
                  Adaptation pillar's degradation endpoint
    - Feature 2: Product catalog with five SKUs across three categories (widgets,
                  gadgets, premium) with unit pricing, reorder points, and
                  reorder quantities
    - Feature 3: Stock reservation system — reserve items against orders with
                  configurable TTL (default 5 minutes), automatic expiry returning
                  stock, and manual release endpoint
    - Feature 4: Low-stock alerting — fires WARNING-severity events to the AREF
                  event bus when stock hits or drops below reorder point, with
                  deduplication to prevent alert storms
    - Feature 5: Stock movement audit trail — every reservation, release, expiry,
                  replenishment, and manual adjustment recorded with timestamp,
                  SKU, delta, reason, and reference (bounded at 5000 entries)
    - Feature 6: Auto-replenishment — POST /inventory/replenish with empty body
                  triggers automatic restock of all SKUs below reorder point
    - Feature 7: Batch stock adjustment — POST /inventory/adjust accepts an array
                  of SKU/delta pairs with a reason for bulk corrections
    - Feature 8: Prometheus metrics — inventory check counter (by result and tier),
                  check latency histogram, degradation tier gauge, reservation
                  counter (by status), per-SKU stock level gauges, low-stock counter
    - Feature 9: Reservation lifecycle tracking — created, expired, and released
                  states all metered through Prometheus counters
    - Feature 10: Inventory statistics — total units, SKU count, total value,
                   category breakdown, low-stock SKU list, active reservations
    - Feature 11: Chaos injection — error and latency fault modes with
                   configurable rate for AREF chaos experiments
    - Feature 12: Degradation-aware inventory checks — behavior changes per tier
                   (reservations disabled in degraded/minimal, pricing omitted
                   in degraded, static responses in minimal)
 
✒ Usage Instructions:
    Start via uvicorn:
        $ uvicorn services.inventory.inventory_app:app --host 0.0.0.0 --port 8003
 
    Or via Docker Compose as part of the AREF microservice stack.
 
✒ Examples:
    # Check inventory
    $ curl -X POST http://localhost:8003/inventory/check \
        -d '{"items":[{"sku":"WIDGET-001","quantity":5}]}'
 
    # Reserve stock
    $ curl -X POST http://localhost:8003/inventory/reserve \
        -d '{"order_id":"ORD-123","items":[{"sku":"WIDGET-001","quantity":5}]}'
 
    # Release reservation
    $ curl -X POST http://localhost:8003/inventory/release/RES-ORD-123-1710000000
 
    # View stock
    $ curl http://localhost:8003/inventory/stock
 
    # Auto-replenish
    $ curl -X POST http://localhost:8003/inventory/replenish -d '{}'
 
    # Batch adjustment
    $ curl -X POST http://localhost:8003/inventory/adjust \
        -d '{"adjustments":[{"sku":"WIDGET-001","delta":-10}],"reason":"damaged"}'
 
    # Set degradation
    $ curl -X POST http://localhost:8003/inventory/degradation \
        -d '{"tier":"degraded"}'
 
    # Stock movements
    $ curl http://localhost:8003/inventory/movements?sku=WIDGET-001
 
    # Statistics
    $ curl http://localhost:8003/inventory/stats
 
✒ Other Important Information:
    - Dependencies:
        Required: fastapi, structlog, prometheus_client
        Internal: services.base, aref.core.events
    - Compatible platforms: Linux, macOS, Docker (Python 3.11+)
    - Performance notes: In-memory storage; reservation expiry is lazy (triggered
      by checks, not background timer); movement log bounded at 5000
    - Security considerations: No authentication; degradation endpoint is
      unauthenticated (intended for Adaptation engine only)
    - Known limitations: In-memory only; catalog is hardcoded; low-stock alert
      dedup resets on restart; no concurrent reservation conflict handling
---------
"""

from __future__ import annotations

import asyncio
import random
import time
from enum import Enum
from typing import Any

import structlog
from fastapi import HTTPException, Request
from prometheus_client import Counter, Gauge, Histogram

from services.base import create_service
from aref.core.events import Event, EventCategory, EventSeverity, get_event_bus

logger = structlog.get_logger(__name__)

app = create_service(
    name="inventory",
    description="Stock management with AREF graceful degradation tiers, reservations, and replenishment",
)


class DegradationTier(str, Enum):
    FULL = "full"
    DEGRADED = "degraded"
    MINIMAL = "minimal"


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
INVENTORY_CHECKS = Counter("inventory_checks_total", "Inventory checks", ["result", "tier"])
INVENTORY_LATENCY = Histogram(
    "inventory_check_latency_seconds", "Check latency",
    buckets=[0.01, 0.05, 0.1, 0.2, 0.5],
)
DEGRADATION_TIER = Gauge("inventory_degradation_tier", "Current degradation tier (0=full, 1=degraded, 2=minimal)")
RESERVATION_COUNTER = Counter("inventory_reservations_total", "Reservations", ["status"])
STOCK_LEVEL = Gauge("inventory_stock_level", "Current stock level", ["sku"])
LOW_STOCK_ALERTS = Counter("inventory_low_stock_alerts_total", "Low stock alerts fired")

# ---------------------------------------------------------------------------
# Product catalog
# ---------------------------------------------------------------------------
_CATALOG: dict[str, dict[str, Any]] = {
    "WIDGET-001": {"name": "Standard Widget",  "category": "widgets",  "unit_price": 9.99,  "reorder_point": 50,  "reorder_qty": 200},
    "WIDGET-002": {"name": "Premium Widget",   "category": "widgets",  "unit_price": 19.99, "reorder_point": 30,  "reorder_qty": 100},
    "GADGET-001": {"name": "Basic Gadget",     "category": "gadgets",  "unit_price": 24.99, "reorder_point": 20,  "reorder_qty": 80},
    "GADGET-002": {"name": "Advanced Gadget",  "category": "gadgets",  "unit_price": 49.99, "reorder_point": 15,  "reorder_qty": 50},
    "PREMIUM-001": {"name": "Elite Component", "category": "premium",  "unit_price": 99.99, "reorder_point": 5,   "reorder_qty": 25},
}

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
_stock: dict[str, int] = {
    "WIDGET-001": 500, "WIDGET-002": 250, "GADGET-001": 100,
    "GADGET-002": 75, "PREMIUM-001": 25,
}
_reservations: dict[str, dict[str, Any]] = {}   # reservation_id -> {order_id, items, created_at, expires_at}
_stock_movements: list[dict[str, Any]] = []      # audit trail
_current_tier = DegradationTier.FULL
_failure_mode: dict[str, Any] = {"enabled": False, "type": None, "rate": 0.0}
_low_stock_fired: set[str] = set()  # track which SKUs already fired alerts

RESERVATION_TTL = 300.0  # 5 minutes

DEGRADATION_TIER.set(0)
for sku, qty in _stock.items():
    STOCK_LEVEL.labels(sku=sku).set(qty)


def _record_movement(sku: str, qty_delta: int, reason: str, ref: str = "") -> None:
    entry = {
        "sku": sku, "qty_delta": qty_delta, "new_qty": _stock.get(sku, 0),
        "reason": reason, "ref": ref, "timestamp": time.time(),
    }
    _stock_movements.append(entry)
    if len(_stock_movements) > 5000:
        _stock_movements.pop(0)
    STOCK_LEVEL.labels(sku=sku).set(_stock.get(sku, 0))


async def _check_low_stock(sku: str) -> None:
    """Fire event bus alert if stock is at or below reorder point."""
    cat = _CATALOG.get(sku)
    if not cat:
        return
    current = _stock.get(sku, 0)
    if current <= cat["reorder_point"] and sku not in _low_stock_fired:
        _low_stock_fired.add(sku)
        LOW_STOCK_ALERTS.inc()
        await get_event_bus().publish(Event(
            category=EventCategory.DETECTION,
            event_type="low_stock_alert",
            severity=EventSeverity.WARNING,
            source="inventory",
            payload={"sku": sku, "current": current, "reorder_point": cat["reorder_point"]},
        ))
        logger.warning("inventory.low_stock", sku=sku, current=current, reorder_point=cat["reorder_point"])
    elif current > cat["reorder_point"] and sku in _low_stock_fired:
        _low_stock_fired.discard(sku)


def _expire_reservations() -> int:
    """Expire stale reservations and return stock."""
    now = time.time()
    expired = []
    for rid, res in list(_reservations.items()):
        if now > res["expires_at"]:
            for item in res["items"]:
                sku, qty = item["sku"], item["quantity"]
                _stock[sku] = _stock.get(sku, 0) + qty
                _record_movement(sku, +qty, "reservation_expired", rid)
            expired.append(rid)
    for rid in expired:
        del _reservations[rid]
        RESERVATION_COUNTER.labels(status="expired").inc()
    return len(expired)


# ---------------------------------------------------------------------------
# Chaos injection
# ---------------------------------------------------------------------------
async def _maybe_inject_chaos() -> None:
    if not _failure_mode["enabled"]:
        return
    if random.random() >= _failure_mode.get("rate", 0.5):
        return
    if _failure_mode["type"] == "error":
        raise HTTPException(status_code=500, detail="Injected inventory failure")
    elif _failure_mode["type"] == "latency":
        await asyncio.sleep(_failure_mode.get("delay", 2.0))


@app.post("/chaos/enable")
async def enable_chaos(request: Request) -> dict[str, Any]:
    global _failure_mode
    body = await request.json()
    _failure_mode = {"enabled": True, "type": body.get("type", "error"),
                     "rate": body.get("rate", 0.5), "delay": body.get("delay", 2.0)}
    return {"status": "chaos_enabled", "mode": _failure_mode}


@app.post("/chaos/disable")
async def disable_chaos() -> dict[str, Any]:
    global _failure_mode
    _failure_mode = {"enabled": False, "type": None, "rate": 0.0}
    return {"status": "chaos_disabled"}


# ---------------------------------------------------------------------------
# Inventory check
# ---------------------------------------------------------------------------
@app.post("/inventory/check")
async def check_inventory(request: Request) -> dict[str, Any]:
    start = time.perf_counter()
    await _maybe_inject_chaos()

    body = await request.json()
    items = body.get("items", [])
    _expire_reservations()

    results = []
    all_available = True

    for item in items:
        sku = item.get("sku", "")
        qty = item.get("quantity", 1)
        cat_info = _CATALOG.get(sku, {})

        if _current_tier == DegradationTier.FULL:
            available = _stock.get(sku, 0)
            in_stock = available >= qty
            results.append({
                "sku": sku, "name": cat_info.get("name", sku),
                "requested": qty, "available": available, "in_stock": in_stock,
                "unit_price": cat_info.get("unit_price", 0),
            })
            if not in_stock:
                all_available = False

        elif _current_tier == DegradationTier.DEGRADED:
            available = _stock.get(sku, 0)
            results.append({
                "sku": sku, "name": cat_info.get("name", sku),
                "requested": qty, "available": available,
                "in_stock": available > 0, "note": "degraded_mode",
            })

        elif _current_tier == DegradationTier.MINIMAL:
            results.append({
                "sku": sku, "name": cat_info.get("name", sku),
                "requested": qty, "available": -1,
                "in_stock": True, "note": "minimal_mode",
            })

    elapsed = time.perf_counter() - start
    INVENTORY_LATENCY.observe(elapsed)
    status = "available" if all_available else "partial"
    INVENTORY_CHECKS.labels(result=status, tier=_current_tier.value).inc()

    return {"items": results, "all_available": all_available, "tier": _current_tier.value}


# ---------------------------------------------------------------------------
# Reservations
# ---------------------------------------------------------------------------
@app.post("/inventory/reserve")
async def reserve_inventory(request: Request) -> dict[str, Any]:
    if _current_tier != DegradationTier.FULL:
        return {"status": "skipped", "reason": f"Reservations disabled in {_current_tier.value} mode"}

    body = await request.json()
    order_id = body.get("order_id", "")
    items = body.get("items", [])
    ttl = body.get("ttl", RESERVATION_TTL)
    reserved = []
    failed = []

    for item in items:
        sku = item.get("sku", "")
        qty = item.get("quantity", 1)
        if _stock.get(sku, 0) >= qty:
            _stock[sku] -= qty
            reserved.append({"sku": sku, "quantity": qty})
            _record_movement(sku, -qty, "reserved", order_id)
            asyncio.ensure_future(_check_low_stock(sku))
        else:
            failed.append({"sku": sku, "requested": qty, "available": _stock.get(sku, 0)})

    now = time.time()
    reservation_id = f"RES-{order_id or 'ANON'}-{int(now)}"
    if reserved:
        _reservations[reservation_id] = {
            "order_id": order_id,
            "items": reserved,
            "created_at": now,
            "expires_at": now + ttl,
        }
        RESERVATION_COUNTER.labels(status="created").inc()

    return {
        "reservation_id": reservation_id,
        "order_id": order_id,
        "reserved": reserved,
        "failed": failed,
        "expires_in": ttl,
    }


@app.post("/inventory/release/{reservation_id}")
async def release_reservation(reservation_id: str) -> dict[str, Any]:
    """Manually release a reservation, returning stock."""
    if reservation_id not in _reservations:
        raise HTTPException(status_code=404, detail="Reservation not found")

    res = _reservations.pop(reservation_id)
    for item in res["items"]:
        sku, qty = item["sku"], item["quantity"]
        _stock[sku] = _stock.get(sku, 0) + qty
        _record_movement(sku, +qty, "released", reservation_id)
    RESERVATION_COUNTER.labels(status="released").inc()

    return {"released": reservation_id, "items": res["items"]}


@app.get("/inventory/reservations")
async def list_reservations() -> dict[str, Any]:
    _expire_reservations()
    return {
        "active": len(_reservations),
        "reservations": list(_reservations.items())[-50:],
    }


# ---------------------------------------------------------------------------
# Stock management
# ---------------------------------------------------------------------------
@app.get("/inventory/stock")
async def get_stock() -> dict[str, Any]:
    return {
        "stock": {
            sku: {
                "quantity": qty,
                **{k: v for k, v in _CATALOG.get(sku, {}).items()},
                "low_stock": qty <= _CATALOG.get(sku, {}).get("reorder_point", 0),
            }
            for sku, qty in _stock.items()
        },
        "tier": _current_tier.value,
        "active_reservations": len(_reservations),
    }


@app.get("/inventory/catalog")
async def get_catalog() -> dict[str, Any]:
    return {"catalog": _CATALOG, "sku_count": len(_CATALOG)}


@app.post("/inventory/replenish")
async def replenish_stock(request: Request) -> dict[str, Any]:
    """Simulate receiving a supply shipment."""
    body = await request.json()
    items = body.get("items", [])
    replenished = []

    if not items:
        # Auto-replenish everything below reorder point
        for sku, cat in _CATALOG.items():
            current = _stock.get(sku, 0)
            if current <= cat["reorder_point"]:
                add_qty = cat["reorder_qty"]
                _stock[sku] = current + add_qty
                replenished.append({"sku": sku, "added": add_qty, "new_qty": _stock[sku]})
                _record_movement(sku, +add_qty, "auto_replenish", "")
                asyncio.ensure_future(_check_low_stock(sku))
    else:
        for item in items:
            sku = item.get("sku", "")
            add_qty = item.get("quantity", 0)
            if sku in _stock and add_qty > 0:
                _stock[sku] += add_qty
                replenished.append({"sku": sku, "added": add_qty, "new_qty": _stock[sku]})
                _record_movement(sku, +add_qty, "manual_replenish", "")
                asyncio.ensure_future(_check_low_stock(sku))

    logger.info("inventory.replenished", count=len(replenished))
    return {"replenished": replenished}


@app.post("/inventory/adjust")
async def adjust_stock(request: Request) -> dict[str, Any]:
    """Batch stock adjustment — positive or negative deltas."""
    body = await request.json()
    adjustments = body.get("adjustments", [])
    reason = body.get("reason", "manual_adjustment")
    results = []

    for adj in adjustments:
        sku = adj.get("sku", "")
        delta = adj.get("delta", 0)
        if sku in _stock:
            _stock[sku] = max(0, _stock[sku] + delta)
            _record_movement(sku, delta, reason, "")
            results.append({"sku": sku, "delta": delta, "new_qty": _stock[sku]})
            asyncio.ensure_future(_check_low_stock(sku))

    return {"adjusted": results}


# ---------------------------------------------------------------------------
# Stock history
# ---------------------------------------------------------------------------
@app.get("/inventory/movements")
async def stock_movements(limit: int = 100, sku: str | None = None) -> dict[str, Any]:
    entries = _stock_movements
    if sku:
        entries = [m for m in entries if m["sku"] == sku]
    return {"movements": entries[-limit:], "total": len(entries)}


# ---------------------------------------------------------------------------
# Degradation control
# ---------------------------------------------------------------------------
@app.post("/inventory/degradation")
async def set_degradation(request: Request) -> dict[str, Any]:
    """Set degradation tier (used by Adaptation pillar)."""
    global _current_tier
    body = await request.json()
    new_tier = body.get("tier", "full")
    try:
        old = _current_tier
        _current_tier = DegradationTier(new_tier)
        tier_value = {"full": 0, "degraded": 1, "minimal": 2}
        DEGRADATION_TIER.set(tier_value.get(new_tier, 0))

        await get_event_bus().publish(Event(
            category=EventCategory.ADAPTATION,
            event_type="degradation_changed",
            severity=EventSeverity.WARNING if new_tier != "full" else EventSeverity.INFO,
            source="inventory",
            payload={"old_tier": old.value, "new_tier": _current_tier.value},
        ))

        logger.info("inventory.degradation_changed", old=old.value, new=_current_tier.value)
        return {"old_tier": old.value, "new_tier": _current_tier.value}
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid tier: {new_tier}")


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------
@app.get("/inventory/stats")
async def inventory_stats() -> dict[str, Any]:
    total_stock = sum(_stock.values())
    total_skus = len(_stock)
    low_stock_skus = [
        sku for sku, qty in _stock.items()
        if qty <= _CATALOG.get(sku, {}).get("reorder_point", 0)
    ]
    by_category: dict[str, int] = {}
    for sku, qty in _stock.items():
        cat = _CATALOG.get(sku, {}).get("category", "unknown")
        by_category[cat] = by_category.get(cat, 0) + qty

    total_value = sum(
        qty * _CATALOG.get(sku, {}).get("unit_price", 0)
        for sku, qty in _stock.items()
    )

    return {
        "total_units": total_stock,
        "total_skus": total_skus,
        "total_value": round(total_value, 2),
        "by_category": by_category,
        "low_stock_skus": low_stock_skus,
        "active_reservations": len(_reservations),
        "tier": _current_tier.value,
        "movements_logged": len(_stock_movements),
    }
