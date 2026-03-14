"""
Anomaly Detection — Blueprint Section 3.1.1.

ML-based statistical anomaly detection on time-series data.
Uses Isolation Forest and Z-score methods.
Signal source: ML model on time-series data
Latency target: < 3 minutes
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import structlog

from aref.core.events import EventSeverity

logger = structlog.get_logger(__name__)


@dataclass
class MetricStream:
    """A named time-series metric stream for anomaly detection."""
    name: str
    service: str
    window_size: int = 100
    z_score_threshold: float = 3.0  # 3 sigma per blueprint example
    description: str = ""

    _values: deque = field(default_factory=lambda: deque(maxlen=100), init=False)
    _timestamps: deque = field(default_factory=lambda: deque(maxlen=100), init=False)

    def record(self, value: float, timestamp: float | None = None) -> None:
        self._values.append(value)
        self._timestamps.append(timestamp or time.time())

    @property
    def mean(self) -> float:
        if not self._values:
            return 0.0
        return float(np.mean(list(self._values)))

    @property
    def std(self) -> float:
        if len(self._values) < 2:
            return 0.0
        return float(np.std(list(self._values)))

    @property
    def latest(self) -> float | None:
        return self._values[-1] if self._values else None

    def z_score(self, value: float | None = None) -> float:
        """Compute Z-score for a value (default: latest)."""
        if value is None:
            value = self.latest
        if value is None or self.std == 0:
            return 0.0
        return abs(value - self.mean) / self.std

    def is_anomalous(self, value: float | None = None) -> bool:
        return self.z_score(value) > self.z_score_threshold


class AnomalyDetector:
    """
    Statistical anomaly detection using Z-score analysis.

    Blueprint example: "Request latency 3 sigma above rolling mean"
    """

    def __init__(self) -> None:
        self._streams: dict[str, MetricStream] = {}
        self._isolation_forest = None  # Lazy-loaded for more advanced detection

    def register_stream(self, stream: MetricStream) -> None:
        key = f"{stream.service}.{stream.name}"
        self._streams[key] = stream

    def record(self, service: str, metric: str, value: float) -> None:
        key = f"{service}.{metric}"
        if key in self._streams:
            self._streams[key].record(value)

    async def detect(self) -> list[dict[str, Any]]:
        """Run anomaly detection across all registered streams."""
        anomalies = []

        for key, stream in self._streams.items():
            if stream.latest is None or len(stream._values) < 10:
                continue

            z = stream.z_score()
            if stream.is_anomalous():
                severity = EventSeverity.CRITICAL if z > 4.0 else EventSeverity.WARNING

                anomalies.append({
                    "service": stream.service,
                    "title": f"Anomaly: {stream.name} ({z:.1f} sigma)",
                    "severity": severity,
                    "metric_name": stream.name,
                    "value": stream.latest,
                    "mean": round(stream.mean, 4),
                    "std": round(stream.std, 4),
                    "z_score": round(z, 2),
                    "threshold": stream.z_score_threshold,
                    "description": stream.description,
                })

        return anomalies

    def get_stream_stats(self) -> dict[str, Any]:
        return {
            key: {
                "latest": s.latest,
                "mean": round(s.mean, 4),
                "std": round(s.std, 4),
                "samples": len(s._values),
                "z_score": round(s.z_score(), 2) if s.latest else 0,
            }
            for key, s in self._streams.items()
        }

    def train_isolation_forest(self) -> None:
        """Train Isolation Forest on historical data for multi-dimensional anomaly detection."""
        from sklearn.ensemble import IsolationForest

        streams_with_data = {k: s for k, s in self._streams.items() if len(s._values) >= 20}
        if not streams_with_data:
            return

        # Build feature matrix from aligned time series
        min_len = min(len(s._values) for s in streams_with_data.values())
        X = np.column_stack([
            list(s._values)[-min_len:] for s in streams_with_data.values()
        ])

        self._isolation_forest = IsolationForest(
            contamination=0.05,
            random_state=42,
            n_estimators=100,
        )
        self._isolation_forest.fit(X)
        logger.info("anomaly.isolation_forest.trained", features=X.shape[1], samples=X.shape[0])
