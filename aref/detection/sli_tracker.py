"""
SLI/SLO Tracking and Error Budget Management.

Implements error budget computation from Blueprint Section 6.2:
  EB_remaining = (1 - SLO) - (t_downtime / t_window)

Tracks SLIs per service and fires alerts when error budgets are depleted.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class SLI:
    """A service level indicator — a quantitative measure of service behavior."""
    name: str
    service: str
    unit: str = ""
    description: str = ""
    _values: list[tuple[float, float]] = field(default_factory=list, init=False)  # (timestamp, value)

    def record(self, value: float) -> None:
        self._values.append((time.time(), value))
        # Keep last 10k samples
        if len(self._values) > 10_000:
            self._values = self._values[-10_000:]

    @property
    def latest(self) -> float | None:
        return self._values[-1][1] if self._values else None

    def values_since(self, since: float) -> list[float]:
        return [v for t, v in self._values if t >= since]


@dataclass
class SLO:
    """A service level objective — a target for an SLI."""
    name: str
    sli_name: str
    service: str
    target: float  # e.g., 0.999 for 99.9%
    window_seconds: float = 2592000.0  # 30 days default
    description: str = ""


class ErrorBudget:
    """Tracks error budget consumption for an SLO."""

    def __init__(self, slo: SLO) -> None:
        self.slo = slo
        self._downtime_seconds: float = 0.0
        self._window_start: float = time.time()

    @property
    def total_budget(self) -> float:
        """Total error budget in seconds for the window."""
        return (1.0 - self.slo.target) * self.slo.window_seconds

    @property
    def remaining(self) -> float:
        """Remaining error budget using blueprint formula."""
        if self.slo.window_seconds == 0:
            return 0.0
        return (1.0 - self.slo.target) - (self._downtime_seconds / self.slo.window_seconds)

    @property
    def consumed_pct(self) -> float:
        if self.total_budget == 0:
            return 100.0
        return (self._downtime_seconds / self.total_budget) * 100.0

    @property
    def is_exhausted(self) -> bool:
        return self.remaining <= 0

    def record_downtime(self, seconds: float) -> None:
        self._downtime_seconds += seconds

    def reset_window(self) -> None:
        self._downtime_seconds = 0.0
        self._window_start = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "slo": self.slo.name,
            "service": self.slo.service,
            "target": self.slo.target,
            "total_budget_seconds": round(self.total_budget, 2),
            "downtime_seconds": round(self._downtime_seconds, 2),
            "remaining": round(self.remaining, 6),
            "consumed_pct": round(self.consumed_pct, 2),
            "is_exhausted": self.is_exhausted,
        }


class SLITracker:
    """
    Manages SLIs, SLOs, and error budgets across all services.
    Central to AREF detection — error budget depletion triggers adaptation.
    """

    def __init__(self) -> None:
        self._slis: dict[str, SLI] = {}
        self._slos: dict[str, SLO] = {}
        self._budgets: dict[str, ErrorBudget] = {}

    def register_sli(self, sli: SLI) -> None:
        key = f"{sli.service}.{sli.name}"
        self._slis[key] = sli

    def register_slo(self, slo: SLO) -> None:
        key = f"{slo.service}.{slo.name}"
        self._slos[key] = slo
        self._budgets[key] = ErrorBudget(slo)

    def record_sli(self, service: str, name: str, value: float) -> None:
        key = f"{service}.{name}"
        if key in self._slis:
            self._slis[key].record(value)

    def record_downtime(self, service: str, slo_name: str, seconds: float) -> None:
        key = f"{service}.{slo_name}"
        if key in self._budgets:
            self._budgets[key].record_downtime(seconds)

    def get_error_budgets(self) -> dict[str, dict[str, Any]]:
        return {key: budget.to_dict() for key, budget in self._budgets.items()}

    def get_exhausted_budgets(self) -> list[dict[str, Any]]:
        return [
            budget.to_dict()
            for budget in self._budgets.values()
            if budget.is_exhausted
        ]

    def get_depleting_budgets(self, threshold_pct: float = 50.0) -> list[dict[str, Any]]:
        """Get budgets that are more than threshold% consumed."""
        return [
            budget.to_dict()
            for budget in self._budgets.values()
            if budget.consumed_pct >= threshold_pct
        ]

    def get_summary(self) -> dict[str, Any]:
        return {
            "slis_tracked": len(self._slis),
            "slos_defined": len(self._slos),
            "budgets": {k: b.to_dict() for k, b in self._budgets.items()},
            "exhausted_count": len(self.get_exhausted_budgets()),
        }
