"""
Detection Engine — Orchestrates all detection classes and manages the detection pipeline.

Responsible for:
  - Running all detectors on their configured intervals
  - Correlating signals across detection classes
  - Managing alert lifecycle (fire, acknowledge, resolve)
  - Computing MTTD and tracking alert fatigue
  - Publishing detection events to the event bus
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import structlog

from aref.core.config import get_config
from aref.core.events import Event, EventBus, EventCategory, EventSeverity, get_event_bus
from aref.core.metrics import ALERT_FIRED, INCIDENTS_DETECTED, get_metrics_engine
from aref.core.models import DetectionClass, Incident, IncidentSeverity

from aref.detection.threshold import ThresholdDetector
from aref.detection.anomaly import AnomalyDetector
from aref.detection.synthetic import SyntheticProber
from aref.detection.sli_tracker import SLITracker

logger = structlog.get_logger(__name__)


class Alert:
    """Represents a fired alert with lifecycle management."""

    def __init__(
        self,
        alert_id: str,
        detection_class: DetectionClass,
        severity: EventSeverity,
        service: str,
        title: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.alert_id = alert_id
        self.detection_class = detection_class
        self.severity = severity
        self.service = service
        self.title = title
        self.details = details or {}
        self.fired_at = time.time()
        self.acknowledged_at: float | None = None
        self.resolved_at: float | None = None
        self.actioned = False

    @property
    def is_active(self) -> bool:
        return self.resolved_at is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "detection_class": self.detection_class.value,
            "severity": self.severity.value,
            "service": self.service,
            "title": self.title,
            "details": self.details,
            "fired_at": self.fired_at,
            "acknowledged_at": self.acknowledged_at,
            "resolved_at": self.resolved_at,
            "actioned": self.actioned,
        }


class DetectionEngine:
    """
    Central detection orchestrator — runs all detection classes,
    correlates signals, and manages the alert pipeline.
    """

    def __init__(self, bus: EventBus | None = None) -> None:
        self.config = get_config().detection
        self.bus = bus or get_event_bus()
        self.metrics = get_metrics_engine()

        # Detection subsystems
        self.threshold = ThresholdDetector()
        self.anomaly = AnomalyDetector()
        self.synthetic = SyntheticProber()
        self.sli_tracker = SLITracker()

        # Alert management
        self._alerts: dict[str, Alert] = {}
        self._alert_counter = 0
        self._weekly_alert_count = 0
        self._week_start = time.time()

        # State
        self._running = False
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        """Start all detection loops."""
        if self._running:
            return
        self._running = True
        logger.info("detection.engine.starting")

        self._tasks = [
            asyncio.create_task(self._threshold_loop()),
            asyncio.create_task(self._anomaly_loop()),
            asyncio.create_task(self._synthetic_loop()),
            asyncio.create_task(self._fatigue_monitor()),
        ]

        await self.bus.publish(Event(
            category=EventCategory.DETECTION,
            event_type="engine_started",
            source="detection_engine",
        ))

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()
        logger.info("detection.engine.stopped")

    async def _threshold_loop(self) -> None:
        while self._running:
            try:
                violations = await self.threshold.check_all()
                for v in violations:
                    await self._fire_alert(
                        detection_class=DetectionClass.THRESHOLD,
                        severity=v.get("severity", EventSeverity.WARNING),
                        service=v.get("service", "unknown"),
                        title=v.get("title", "Threshold breach"),
                        details=v,
                    )
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("detection.threshold_loop.error")
            await asyncio.sleep(self.config.threshold_check_interval)

    async def _anomaly_loop(self) -> None:
        while self._running:
            try:
                anomalies = await self.anomaly.detect()
                for a in anomalies:
                    await self._fire_alert(
                        detection_class=DetectionClass.ANOMALY,
                        severity=a.get("severity", EventSeverity.WARNING),
                        service=a.get("service", "unknown"),
                        title=a.get("title", "Anomaly detected"),
                        details=a,
                    )
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("detection.anomaly_loop.error")
            await asyncio.sleep(self.config.anomaly_check_interval)

    async def _synthetic_loop(self) -> None:
        while self._running:
            try:
                failures = await self.synthetic.probe_all()
                for f in failures:
                    await self._fire_alert(
                        detection_class=DetectionClass.SYNTHETIC,
                        severity=EventSeverity.CRITICAL,
                        service=f.get("service", "unknown"),
                        title=f"Synthetic probe failed: {f.get('service', 'unknown')}",
                        details=f,
                    )
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("detection.synthetic_loop.error")
            await asyncio.sleep(self.config.synthetic_probe_interval)

    async def _fatigue_monitor(self) -> None:
        """Monitor alert fatigue — blueprint anti-pattern: > 50 alerts/week."""
        while self._running:
            try:
                now = time.time()
                if now - self._week_start > 604800:  # 7 days
                    if self._weekly_alert_count > self.config.alert_fatigue_max_per_week:
                        logger.warning(
                            "detection.alert_fatigue",
                            weekly_count=self._weekly_alert_count,
                            threshold=self.config.alert_fatigue_max_per_week,
                        )
                        await self.bus.publish(Event(
                            category=EventCategory.DETECTION,
                            event_type="alert_fatigue_warning",
                            severity=EventSeverity.WARNING,
                            source="detection_engine",
                            payload={"weekly_count": self._weekly_alert_count},
                        ))
                    self._weekly_alert_count = 0
                    self._week_start = now
            except asyncio.CancelledError:
                break
            await asyncio.sleep(3600)  # Check hourly

    async def _fire_alert(
        self,
        detection_class: DetectionClass,
        severity: EventSeverity,
        service: str,
        title: str,
        details: dict[str, Any],
    ) -> Alert:
        self._alert_counter += 1
        self._weekly_alert_count += 1
        alert_id = f"ALT-{self._alert_counter:06d}"

        alert = Alert(
            alert_id=alert_id,
            detection_class=detection_class,
            severity=severity,
            service=service,
            title=title,
            details=details,
        )
        self._alerts[alert_id] = alert

        ALERT_FIRED.labels(severity=severity.value, service=service).inc()
        INCIDENTS_DETECTED.labels(detection_class=detection_class.value).inc()

        await self.bus.publish(Event(
            category=EventCategory.DETECTION,
            event_type="alert_fired",
            severity=severity,
            source="detection_engine",
            payload=alert.to_dict(),
        ))

        logger.info(
            "detection.alert_fired",
            alert_id=alert_id,
            class_=detection_class.value,
            severity=severity.value,
            service=service,
            title=title,
        )

        return alert

    def acknowledge_alert(self, alert_id: str) -> bool:
        alert = self._alerts.get(alert_id)
        if alert and alert.is_active:
            alert.acknowledged_at = time.time()
            return True
        return False

    def resolve_alert(self, alert_id: str, actioned: bool = True) -> bool:
        alert = self._alerts.get(alert_id)
        if alert and alert.is_active:
            alert.resolved_at = time.time()
            alert.actioned = actioned
            return True
        return False

    def get_active_alerts(self) -> list[dict[str, Any]]:
        return [a.to_dict() for a in self._alerts.values() if a.is_active]

    def get_alert_stats(self) -> dict[str, Any]:
        active = [a for a in self._alerts.values() if a.is_active]
        total_actioned = sum(1 for a in self._alerts.values() if a.actioned)
        total_resolved = sum(1 for a in self._alerts.values() if a.resolved_at)
        ratio = (total_actioned / total_resolved) if total_resolved > 0 else 0

        return {
            "total_alerts": len(self._alerts),
            "active_alerts": len(active),
            "weekly_count": self._weekly_alert_count,
            "alert_to_action_ratio": round(ratio, 2),
            "fatigue_threshold": self.config.alert_fatigue_max_per_week,
        }
