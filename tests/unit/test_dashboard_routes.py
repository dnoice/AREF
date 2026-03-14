"""
Tests for AREF dashboard API routes — status, pillars, metrics, chaos.

Uses a minimal FastAPI app with routers mounted directly, bypassing
the full lifespan to avoid external service dependencies.
"""

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aref.core.config import get_config, reset_config
from aref.core.events import get_event_bus, reset_event_bus, Event, EventCategory, EventSeverity
from aref.dashboard.engines import EngineContainer, get_engines, set_engines

from aref.detection.engine import DetectionEngine
from aref.adaptation.engine import AdaptationEngine
from aref.recovery.engine import RecoveryEngine
from aref.evolution.engine import EvolutionEngine
from aref.maturity.model import MaturityAssessor
from aref.absorption.bulkhead import BulkheadManager
from aref.absorption.rate_limiter import RateLimiterManager
from aref.absorption.blast_radius import BlastRadiusAnalyzer
from aref.absorption.degradation import DegradationManager
from chaos.injector import FaultInjector
from chaos.experiments import ExperimentRunner

from aref.dashboard.routes.status import router as status_router
from aref.dashboard.routes.pillars import router as pillars_router
from aref.dashboard.routes.metrics import router as metrics_router
from aref.dashboard.routes.chaos import router as chaos_router


@pytest.fixture
def dashboard_client():
    """Create a test client with initialized engines but no lifespan."""
    reset_config()
    reset_event_bus()
    bus = get_event_bus()

    container = EngineContainer()
    container.detection_engine = DetectionEngine(bus)
    container.adaptation_engine = AdaptationEngine(bus)
    container.recovery_engine = RecoveryEngine(bus)
    container.evolution_engine = EvolutionEngine(bus)
    container.fault_injector = FaultInjector()
    container.experiment_runner = ExperimentRunner(container.fault_injector)
    container.maturity_assessor = MaturityAssessor()
    container.rate_limiter_mgr = RateLimiterManager()
    container.bulkhead_mgr = BulkheadManager()
    container.blast_radius = BlastRadiusAnalyzer()
    container.degradation_mgr = DegradationManager()
    set_engines(container)

    app = FastAPI()
    app.include_router(status_router)
    app.include_router(pillars_router)
    app.include_router(metrics_router)
    app.include_router(chaos_router)

    return TestClient(app)


class TestStatusRoutes:
    def test_get_status(self, dashboard_client):
        resp = dashboard_client.get("/api/aref/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "crs" in data
        assert "pillars" in data
        assert "risk_profile" in data
        assert "timestamp" in data
        assert set(data["pillars"].keys()) == {"detection", "absorption", "adaptation", "recovery", "evolution"}

    def test_get_alerts(self, dashboard_client):
        resp = dashboard_client.get("/api/aref/alerts")
        assert resp.status_code == 200
        data = resp.json()
        assert "alerts" in data
        assert "stats" in data

    def test_get_timeline(self, dashboard_client):
        resp = dashboard_client.get("/api/aref/timeline")
        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data
        assert "summary" in data
        assert "total" in data["summary"]


class TestPillarRoutes:
    def test_detection_status(self, dashboard_client):
        resp = dashboard_client.get("/api/aref/detection")
        assert resp.status_code == 200
        data = resp.json()
        assert "alerts" in data
        assert "config" in data

    def test_absorption_status(self, dashboard_client):
        resp = dashboard_client.get("/api/aref/absorption")
        assert resp.status_code == 200
        data = resp.json()
        assert "circuit_breakers" in data
        assert "config" in data

    def test_adaptation_status(self, dashboard_client):
        resp = dashboard_client.get("/api/aref/adaptation")
        assert resp.status_code == 200
        data = resp.json()
        assert "config" in data

    def test_recovery_status(self, dashboard_client):
        resp = dashboard_client.get("/api/aref/recovery")
        assert resp.status_code == 200
        data = resp.json()
        assert "runbooks" in data
        assert "tier_targets" in data
        assert "config" in data

    def test_evolution_status(self, dashboard_client):
        resp = dashboard_client.get("/api/aref/evolution")
        assert resp.status_code == 200
        data = resp.json()
        assert "action_items" in data
        assert "review_process" in data
        assert len(data["review_process"]) == 6


class TestMetricsRoutes:
    def test_get_maturity(self, dashboard_client):
        resp = dashboard_client.get("/api/aref/maturity")
        assert resp.status_code == 200
        data = resp.json()
        assert "assessments" in data
        assert "crs_scores" in data
        assert "overall_level" in data

    def test_get_metrics(self, dashboard_client):
        resp = dashboard_client.get("/api/aref/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert "pillar_scores" in data
        assert "crs_profiles" in data
        assert "error_budgets" in data
        assert "targets" in data
        # Verify all risk profiles present
        assert len(data["crs_profiles"]) == 4


class TestChaosRoutes:
    def test_chaos_status(self, dashboard_client):
        resp = dashboard_client.get("/api/aref/chaos/status")
        assert resp.status_code == 200

    def test_chaos_start_unknown_experiment(self, dashboard_client):
        resp = dashboard_client.post(
            "/api/aref/chaos/start",
            json={"experiment": "nonexistent_experiment"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data

    def test_chaos_stop(self, dashboard_client):
        resp = dashboard_client.post("/api/aref/chaos/stop")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "stopped"
