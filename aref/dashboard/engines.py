"""
✒ Metadata
    - Title: Engine Container (AREF Edition - v2.0)
    - File Name: engines.py
    - Relative Path: aref/dashboard/engines.py
    - Artifact Type: script
    - Version: 2.0.0
    - Date: 2026-03-13
    - Update: Thursday, March 13, 2026
    - Author: Dennis 'dnoice' Smaltz
    - A.I. Acknowledgement: Anthropic - Claude Opus 4
    - Signature: ︻デ═─── ✦ ✦ ✦ | Aim Twice, Shoot Once!

✒ Description:
    Centralized container for all AREF engine instances. Replaces scattered
    module-level global variables with a single, structured container accessed
    via get_engines() / set_engines().

✒ Key Features:
    - Feature 1: Dataclass container holding all 11 engine instances
    - Feature 2: Module-level singleton with get/set accessors
    - Feature 3: Eliminates 'global' keyword usage in app.py

✒ Usage Instructions:
    In lifespan:
        container = EngineContainer(...)
        set_engines(container)

    In route handlers:
        e = get_engines()
        e.detection_engine.get_status()
---------
"""

from __future__ import annotations

from dataclasses import dataclass, field

from aref.detection.engine import DetectionEngine
from aref.absorption.bulkhead import BulkheadManager
from aref.absorption.rate_limiter import RateLimiterManager
from aref.absorption.blast_radius import BlastRadiusAnalyzer
from aref.absorption.degradation import DegradationManager
from aref.adaptation.engine import AdaptationEngine
from aref.recovery.engine import RecoveryEngine
from aref.evolution.engine import EvolutionEngine
from aref.maturity.model import MaturityAssessor
from chaos.injector import FaultInjector
from chaos.experiments import ExperimentRunner


@dataclass
class EngineContainer:
    """Holds references to all AREF engine instances."""

    detection_engine: DetectionEngine | None = None
    adaptation_engine: AdaptationEngine | None = None
    recovery_engine: RecoveryEngine | None = None
    evolution_engine: EvolutionEngine | None = None
    fault_injector: FaultInjector | None = None
    experiment_runner: ExperimentRunner | None = None
    maturity_assessor: MaturityAssessor | None = None
    rate_limiter_mgr: RateLimiterManager | None = None
    bulkhead_mgr: BulkheadManager | None = None
    blast_radius: BlastRadiusAnalyzer | None = None
    degradation_mgr: DegradationManager | None = None


_engines: EngineContainer = EngineContainer()


def get_engines() -> EngineContainer:
    """Return the global engine container."""
    return _engines


def set_engines(container: EngineContainer) -> None:
    """Replace the global engine container."""
    global _engines
    _engines = container
