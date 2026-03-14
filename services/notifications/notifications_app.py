"""
✒ Metadata
    - Title: Notification Service (AREF Edition - v2.0)
    - File Name: notifications_app.py
    - Relative Path: services/notifications/notifications_app.py
    - Artifact Type: script
    - Version: 2.0.0
    - Date: 2026-03-13
    - Update: Thursday, March 13, 2026
    - Author: Dennis 'dnoice' Smaltz
    - A.I. Acknowledgement: Anthropic - Claude Opus 4
    - Signature: ︻デ═─── ✦ ✦ ✦ | Aim Twice, Shoot Once!

✒ Description:
    Multi-channel async notification dispatch microservice. Intentionally the
    "least critical" service in the AREF platform to demonstrate feature flagging,
    load shedding, and cognitive load reduction during incidents. Supports email,
    SMS, push, and webhook channels with priority-based shedding and retry with
    exponential backoff.

✒ Key Features:
    - Feature 1: Four notification channels — email, sms, push, webhook — each
                  with distinct latency profiles, failure rates, and cost models
    - Feature 2: Priority levels (critical, high, normal, low) with configurable
                  shedding aggressiveness: none → low → non_critical → all
    - Feature 3: Retry with exponential backoff — up to 3 attempts for non-low
                  priority notifications, with per-attempt metric tracking
    - Feature 4: Six notification templates — order_confirmation, payment_receipt,
                  shipping_update, low_stock_alert, incident_alert, general — with
                  placeholder substitution from request body
    - Feature 5: Delivery tracking — queued_at, delivered_at, failed_at timestamps,
                  attempt counts, and per-notification status lifecycle
    - Feature 6: Queue buffering (Absorption pillar) — bounded deque with 10K max
                  capacity, auto-drops oldest when full, depth gauge metric
    - Feature 7: Load shedding (Adaptation pillar) — global enable/disable toggle
                  and granular shed-level control via /notifications/shed-level
    - Feature 8: Batch notification endpoint for sending multiple at once
    - Feature 9: Comprehensive statistics — by status, channel, type, priority,
                  delivery rate, average latency, retry count, queue depth
    - Feature 10: AREF event bus integration — publishes notification_failed and
                   notification_shedding events for Detection and Adaptation pillars
    - Feature 11: Prometheus metrics — notifications_sent_total (by type/channel/
                   status), queue_depth gauge, delivery_latency_seconds histogram,
                   shed_total counter, retries_total counter
    - Feature 12: Chaos injection — error-type fault mode with configurable rate
                   for testing delivery failure paths

✒ Usage Instructions:
    Start via uvicorn:
        $ uvicorn services.notifications.notifications_app:app --host 0.0.0.0 --port 8004

    Or via Docker Compose as part of the AREF microservice stack.

✒ Examples:
    # Send notification
    $ curl -X POST http://localhost:8004/notifications \
        -d '{"type":"order_confirmation","channel":"email","recipient":"user@example.com","order_id":"ORD-123","total":"49.99"}'

    # Send high-priority SMS
    $ curl -X POST http://localhost:8004/notifications \
        -d '{"type":"incident_alert","channel":"sms","priority":"critical","recipient":"+1234567890","service":"payments","status":"down"}'

    # Batch notifications
    $ curl -X POST http://localhost:8004/notifications/batch \
        -d '{"notifications":[{"type":"general","channel":"push","recipient":"all","message":"System maintenance"}]}'

    # Set shedding level during incident
    $ curl -X POST http://localhost:8004/notifications/shed-level \
        -d '{"level":"non_critical"}'

    # View stats
    $ curl http://localhost:8004/notifications/stats

    # View templates
    $ curl http://localhost:8004/notifications/templates

✒ Other Important Information:
    - Dependencies:
        Required: fastapi, structlog, prometheus_client
        Internal: services.base, aref.core.events
    - Compatible platforms: Linux, macOS, Docker (Python 3.11+)
    - SLIs:
        Notification delivery rate (> 95%)
        Queue depth (< 1000 pending)
        Delivery latency (p99 < 5s)
    - Performance notes: Async fire-and-forget delivery via asyncio.create_task;
      queue bounded at 10K entries; sent history bounded at 5K entries
    - Security considerations: No authentication on toggle/shed-level endpoints;
      recipients not validated; template substitution is plain string replacement
    - Known limitations: In-memory queue (not persistent); no dead-letter queue;
      channel simulation only (no actual email/SMS delivery); retry backoff is
      per-delivery not per-channel
---------
"""

from __future__ import annotations

import asyncio
import random
import time
import uuid
from collections import deque
from typing import Any

import structlog
from fastapi import Request
from prometheus_client import Counter, Gauge, Histogram

from services.base import create_service
from services.state import BoundedLog
from aref.core.events import Event, EventCategory, EventSeverity, get_event_bus

logger = structlog.get_logger(__name__)

app = create_service(
    name="notifications",
    description="Multi-channel async notification dispatch with priority, retry, and load shedding",
)

# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
NOTIFICATIONS_SENT = Counter("notifications_sent_total", "Notifications sent", ["type", "channel", "status"])
QUEUE_DEPTH = Gauge("notifications_queue_depth", "Pending notification queue depth")
DELIVERY_LATENCY = Histogram(
    "notifications_delivery_latency_seconds", "Delivery latency",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)
SHED_COUNTER = Counter("notifications_shed_total", "Notifications shed during incidents", ["reason"])
RETRY_COUNTER = Counter("notifications_retries_total", "Retry attempts")

# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------
TEMPLATES: dict[str, dict[str, str]] = {
    "order_confirmation": {
        "subject": "Order Confirmed",
        "body": "Your order {order_id} has been confirmed. Total: ${total}.",
        "channels": "email,push",
    },
    "payment_receipt": {
        "subject": "Payment Received",
        "body": "Payment of ${amount} for order {order_id} processed via {provider}.",
        "channels": "email",
    },
    "shipping_update": {
        "subject": "Order Shipped",
        "body": "Your order {order_id} has been shipped. Tracking: {tracking_id}.",
        "channels": "email,sms,push",
    },
    "low_stock_alert": {
        "subject": "Low Stock Alert",
        "body": "SKU {sku} is at {current} units (reorder point: {reorder_point}).",
        "channels": "email,webhook",
    },
    "incident_alert": {
        "subject": "Incident Detected",
        "body": "Service {service} has entered {status} state. Action required.",
        "channels": "email,sms,push,webhook",
    },
    "general": {
        "subject": "Notification",
        "body": "{message}",
        "channels": "email",
    },
}

# Channel simulation configs
CHANNEL_CONFIG: dict[str, dict[str, Any]] = {
    "email":   {"latency_base": 0.2,  "failure_rate": 0.02, "cost": 0.001},
    "sms":     {"latency_base": 0.3,  "failure_rate": 0.05, "cost": 0.01},
    "push":    {"latency_base": 0.05, "failure_rate": 0.03, "cost": 0.0001},
    "webhook": {"latency_base": 0.1,  "failure_rate": 0.01, "cost": 0.0},
}

PRIORITY_ORDER = {"critical": 0, "high": 1, "normal": 2, "low": 3}

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
_queue: deque[dict[str, Any]] = deque(maxlen=10_000)
_sent: BoundedLog[dict[str, Any]] = BoundedLog(max_entries=5000)
_enabled = True
_shed_level = "none"   # none, low, non_critical, all
_max_retries = 3


def _should_shed(priority: str) -> bool:
    """Determine if a notification should be shed based on current incident level."""
    if _shed_level == "none":
        return False
    if _shed_level == "low":
        return priority == "low"
    if _shed_level == "non_critical":
        return priority in ("low", "normal")
    if _shed_level == "all":
        return True
    return False


# ---------------------------------------------------------------------------
# Core dispatch
# ---------------------------------------------------------------------------
async def _deliver(notification: dict[str, Any]) -> None:
    """Simulate delivering a notification through its channel with retry."""
    channel = notification.get("channel", "email")
    ch_cfg = CHANNEL_CONFIG.get(channel, CHANNEL_CONFIG["email"])
    ntf_type = notification.get("type", "general")
    max_attempts = _max_retries if notification.get("priority", "normal") != "low" else 1

    for attempt in range(1, max_attempts + 1):
        notification["attempts"] = attempt
        latency = ch_cfg["latency_base"] + random.uniform(0, 0.15)
        await asyncio.sleep(latency)

        # Chaos injection (uses shared chaos mode from base factory)
        chaos = app.state.chaos_mode
        chaos_fail = (
            chaos["enabled"]
            and random.random() < chaos.get("rate", 0.3)
        )
        natural_fail = random.random() < ch_cfg["failure_rate"]

        if chaos_fail or natural_fail:
            if attempt < max_attempts:
                RETRY_COUNTER.inc()
                backoff = 0.2 * (2 ** (attempt - 1))
                logger.debug("notification.retry", ntf_id=notification["notification_id"],
                             attempt=attempt, backoff=f"{backoff:.2f}s")
                await asyncio.sleep(backoff)
                continue
            else:
                notification["status"] = "failed"
                notification["failed_at"] = time.time()
                NOTIFICATIONS_SENT.labels(type=ntf_type, channel=channel, status="failed").inc()
                DELIVERY_LATENCY.observe(time.time() - notification["queued_at"])

                await get_event_bus().publish(Event(
                    category=EventCategory.SYSTEM,
                    event_type="notification_failed",
                    severity=EventSeverity.WARNING,
                    source="notifications",
                    payload={"notification_id": notification["notification_id"],
                             "channel": channel, "attempts": attempt},
                ))
                break
        else:
            notification["status"] = "delivered"
            notification["delivered_at"] = time.time()
            NOTIFICATIONS_SENT.labels(type=ntf_type, channel=channel, status="delivered").inc()
            DELIVERY_LATENCY.observe(time.time() - notification["queued_at"])
            break

    _sent.append(notification)
    if notification in _queue:
        _queue.remove(notification)
    QUEUE_DEPTH.set(len(_queue))


# ---------------------------------------------------------------------------
# Send endpoint
# ---------------------------------------------------------------------------
@app.post("/notifications")
async def send_notification(request: Request) -> dict[str, Any]:
    body = await request.json()
    priority = body.get("priority", "normal")
    channel = body.get("channel", "email")
    ntf_type = body.get("type", "general")

    if not _enabled:
        SHED_COUNTER.labels(reason="disabled").inc()
        return {"status": "shed", "reason": "Notifications disabled during incident"}

    if _should_shed(priority):
        SHED_COUNTER.labels(reason=f"shed_{_shed_level}").inc()
        return {"status": "shed", "reason": f"Priority '{priority}' shed at level '{_shed_level}'"}

    # Resolve template
    template = TEMPLATES.get(ntf_type, TEMPLATES["general"])
    subject = template["subject"]
    msg_body = template["body"]
    for k, v in body.items():
        msg_body = msg_body.replace(f"{{{k}}}", str(v))

    now = time.time()
    notification = {
        "notification_id": f"NTF-{uuid.uuid4().hex[:8].upper()}",
        "order_id": body.get("order_id", ""),
        "type": ntf_type,
        "channel": channel,
        "priority": priority,
        "recipient": body.get("recipient", ""),
        "subject": subject,
        "body": msg_body,
        "status": "queued",
        "attempts": 0,
        "queued_at": now,
        "correlation_id": request.headers.get("X-Correlation-ID", ""),
    }

    _queue.append(notification)
    QUEUE_DEPTH.set(len(_queue))
    asyncio.create_task(_deliver(notification))

    return notification


@app.post("/notifications/batch")
async def send_batch(request: Request) -> dict[str, Any]:
    """Send multiple notifications at once."""
    body = await request.json()
    notifications = body.get("notifications", [])
    results = []

    for ntf_body in notifications:
        priority = ntf_body.get("priority", "normal")
        channel = ntf_body.get("channel", "email")
        ntf_type = ntf_body.get("type", "general")

        if not _enabled or _should_shed(priority):
            results.append({"status": "shed", "type": ntf_type})
            continue

        template = TEMPLATES.get(ntf_type, TEMPLATES["general"])
        msg_body = template["body"]
        for k, v in ntf_body.items():
            msg_body = msg_body.replace(f"{{{k}}}", str(v))

        now = time.time()
        notification = {
            "notification_id": f"NTF-{uuid.uuid4().hex[:8].upper()}",
            "order_id": ntf_body.get("order_id", ""),
            "type": ntf_type,
            "channel": channel,
            "priority": priority,
            "recipient": ntf_body.get("recipient", ""),
            "subject": template["subject"],
            "body": msg_body,
            "status": "queued",
            "attempts": 0,
            "queued_at": now,
        }
        _queue.append(notification)
        asyncio.create_task(_deliver(notification))
        results.append(notification)

    QUEUE_DEPTH.set(len(_queue))
    return {"queued": len([r for r in results if isinstance(r, dict) and r.get("status") == "queued"]),
            "shed": len([r for r in results if isinstance(r, dict) and r.get("status") == "shed"]),
            "results": results}


# ---------------------------------------------------------------------------
# Query endpoints
# ---------------------------------------------------------------------------
@app.get("/notifications/queue")
async def get_queue() -> dict[str, Any]:
    return {"queue_depth": len(_queue), "items": list(_queue)[-20:]}


@app.get("/notifications/history")
async def get_history(limit: int = 50, status: str | None = None, channel: str | None = None) -> dict[str, Any]:
    entries = _sent
    if status:
        entries = [n for n in entries if n.get("status") == status]
    if channel:
        entries = [n for n in entries if n.get("channel") == channel]
    return {"notifications": entries[-limit:], "total_sent": len(_sent)}


@app.get("/notifications/templates")
async def get_templates() -> dict[str, Any]:
    return {"templates": TEMPLATES}


# ---------------------------------------------------------------------------
# Shedding / toggle controls
# ---------------------------------------------------------------------------
@app.post("/notifications/toggle")
async def toggle_notifications(request: Request) -> dict[str, Any]:
    """Enable/disable notifications (used by Adaptation pillar for load shedding)."""
    global _enabled
    body = await request.json()
    _enabled = body.get("enabled", True)
    logger.info("notifications.toggled", enabled=_enabled)
    return {"enabled": _enabled}


@app.post("/notifications/shed-level")
async def set_shed_level(request: Request) -> dict[str, Any]:
    """Set shedding aggressiveness: none, low, non_critical, all."""
    global _shed_level
    body = await request.json()
    new_level = body.get("level", "none")
    if new_level not in ("none", "low", "non_critical", "all"):
        return {"error": f"Invalid level: {new_level}. Use: none, low, non_critical, all"}
    old = _shed_level
    _shed_level = new_level
    logger.info("notifications.shed_level_changed", old=old, new=_shed_level)

    if new_level != "none":
        await get_event_bus().publish(Event(
            category=EventCategory.ADAPTATION,
            event_type="notification_shedding",
            severity=EventSeverity.WARNING,
            source="notifications",
            payload={"old_level": old, "new_level": new_level},
        ))

    return {"old_level": old, "new_level": _shed_level}


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------
@app.get("/notifications/stats")
async def notification_stats() -> dict[str, Any]:
    if not _sent:
        return {"total": 0, "by_status": {}, "by_channel": {}, "by_type": {}, "delivery_rate": 0}

    by_status: dict[str, int] = {}
    by_channel: dict[str, int] = {}
    by_type: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    latencies: list[float] = []
    retry_sum = 0

    for n in _sent:
        st = n.get("status", "unknown")
        by_status[st] = by_status.get(st, 0) + 1
        ch = n.get("channel", "email")
        by_channel[ch] = by_channel.get(ch, 0) + 1
        tp = n.get("type", "general")
        by_type[tp] = by_type.get(tp, 0) + 1
        pr = n.get("priority", "normal")
        by_priority[pr] = by_priority.get(pr, 0) + 1
        retry_sum += max(0, n.get("attempts", 1) - 1)

        if n.get("delivered_at") and n.get("queued_at"):
            latencies.append(n["delivered_at"] - n["queued_at"])

    total = len(_sent)
    delivered = by_status.get("delivered", 0)

    return {
        "total": total,
        "by_status": by_status,
        "by_channel": by_channel,
        "by_type": by_type,
        "by_priority": by_priority,
        "delivery_rate": round(delivered / max(total, 1), 4),
        "avg_latency_s": round(sum(latencies) / max(len(latencies), 1), 3) if latencies else 0,
        "total_retries": retry_sum,
        "queue_depth": len(_queue),
        "enabled": _enabled,
        "shed_level": _shed_level,
    }
