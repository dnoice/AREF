"""
Feature Flag System — Blueprint Section 3.3.1.

Strategy: Disable non-essential features when error budget is depleted.
Trigger: Error budget depletion
Rollback risk: Low
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from aref.core.metrics import FEATURE_FLAGS_TOGGLED

logger = structlog.get_logger(__name__)


@dataclass
class FeatureFlag:
    name: str
    service: str
    enabled: bool = True
    critical: bool = False  # Critical flags cannot be auto-disabled
    description: str = ""
    _history: list[dict[str, Any]] = field(default_factory=list, init=False)

    def toggle(self, enabled: bool, reason: str = "") -> None:
        old = self.enabled
        self.enabled = enabled
        action = "enabled" if enabled else "disabled"
        FEATURE_FLAGS_TOGGLED.labels(flag=self.name, action=action).inc()
        self._history.append({
            "timestamp": time.time(),
            "old": old,
            "new": enabled,
            "reason": reason,
        })


class FeatureFlagManager:
    """Manages feature flags across all services for load shedding."""

    def __init__(self) -> None:
        self._flags: dict[str, FeatureFlag] = {}

    def register(self, flag: FeatureFlag) -> None:
        self._flags[flag.name] = flag

    def is_enabled(self, name: str) -> bool:
        flag = self._flags.get(name)
        return flag.enabled if flag else True

    def enable(self, name: str, reason: str = "") -> bool:
        flag = self._flags.get(name)
        if flag:
            flag.toggle(True, reason)
            logger.info("feature_flag.enabled", flag=name, reason=reason)
            return True
        return False

    def disable(self, name: str, reason: str = "") -> bool:
        flag = self._flags.get(name)
        if flag:
            if flag.critical:
                logger.warning("feature_flag.critical_cannot_disable", flag=name)
                return False
            flag.toggle(False, reason)
            logger.info("feature_flag.disabled", flag=name, reason=reason)
            return True
        return False

    def shed_non_critical(self, service: str | None = None, reason: str = "load_shedding") -> list[str]:
        """Disable all non-critical flags, optionally filtered by service."""
        shed = []
        for name, flag in self._flags.items():
            if not flag.critical and flag.enabled:
                if service is None or flag.service == service:
                    flag.toggle(False, reason)
                    shed.append(name)
        logger.info("feature_flag.shed_non_critical", count=len(shed), service=service)
        return shed

    def restore_all(self, service: str | None = None) -> list[str]:
        """Re-enable all flags, optionally filtered by service."""
        restored = []
        for name, flag in self._flags.items():
            if not flag.enabled:
                if service is None or flag.service == service:
                    flag.toggle(True, "restored")
                    restored.append(name)
        return restored

    def get_status(self) -> dict[str, Any]:
        return {
            "total": len(self._flags),
            "enabled": sum(1 for f in self._flags.values() if f.enabled),
            "disabled": sum(1 for f in self._flags.values() if not f.enabled),
            "flags": {
                name: {
                    "enabled": f.enabled,
                    "critical": f.critical,
                    "service": f.service,
                }
                for name, f in self._flags.items()
            },
        }
