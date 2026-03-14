"""
Threshold-Based Detection — Blueprint Section 3.1.1.

Monitors numeric metrics against configurable thresholds.
Signal source: Metrics / KPIs
Latency target: < 1 minute
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

import structlog

from aref.core.events import EventSeverity

logger = structlog.get_logger(__name__)


@dataclass
class ThresholdRule:
    name: str
    service: str
    metric_fn: Callable[[], float | None]
    warning_threshold: float
    critical_threshold: float
    comparison: str = "gt"  # "gt" = fire when metric > threshold, "lt" = fire when metric < threshold
    consecutive_samples: int = 3
    description: str = ""

    # Internal state
    _breach_count: int = field(default=0, init=False)
    _last_value: float | None = field(default=None, init=False)


class ThresholdDetector:
    """Monitors metrics against thresholds with consecutive-sample confirmation."""

    def __init__(self) -> None:
        self._rules: list[ThresholdRule] = []
        self._registered_services: set[str] = set()

    def add_rule(self, rule: ThresholdRule) -> None:
        self._rules.append(rule)
        self._registered_services.add(rule.service)

    def remove_rule(self, name: str) -> None:
        self._rules = [r for r in self._rules if r.name != name]

    async def check_all(self) -> list[dict[str, Any]]:
        """Check all threshold rules. Returns list of violations."""
        violations = []

        for rule in self._rules:
            try:
                value = rule.metric_fn()
                if value is None:
                    continue

                rule._last_value = value
                breached = False

                if rule.comparison == "gt":
                    breached = value > rule.critical_threshold or value > rule.warning_threshold
                elif rule.comparison == "lt":
                    breached = value < rule.critical_threshold or value < rule.warning_threshold

                if breached:
                    rule._breach_count += 1
                else:
                    rule._breach_count = 0
                    continue

                if rule._breach_count >= rule.consecutive_samples:
                    is_critical = (
                        (rule.comparison == "gt" and value > rule.critical_threshold)
                        or (rule.comparison == "lt" and value < rule.critical_threshold)
                    )
                    severity = EventSeverity.CRITICAL if is_critical else EventSeverity.WARNING

                    violations.append({
                        "service": rule.service,
                        "title": f"Threshold breach: {rule.name}",
                        "severity": severity,
                        "metric_name": rule.name,
                        "value": value,
                        "warning_threshold": rule.warning_threshold,
                        "critical_threshold": rule.critical_threshold,
                        "consecutive_breaches": rule._breach_count,
                        "description": rule.description,
                    })

            except Exception:
                logger.exception("threshold.check_error", rule=rule.name)

        return violations

    def get_status(self) -> dict[str, Any]:
        return {
            "rules_count": len(self._rules),
            "services_monitored": list(self._registered_services),
            "rules": [
                {
                    "name": r.name,
                    "service": r.service,
                    "last_value": r._last_value,
                    "breach_count": r._breach_count,
                }
                for r in self._rules
            ],
        }
