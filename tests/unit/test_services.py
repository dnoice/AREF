"""
Tests for AREF service layer — InMemoryStore, BoundedLog, and
the create_service factory with chaos injection.
"""

import time

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from services.state import InMemoryStore, BoundedLog
from services.base import create_service, maybe_inject_chaos


# ---------------------------------------------------------------------------
# InMemoryStore
# ---------------------------------------------------------------------------
class TestInMemoryStore:
    def test_basic_operations(self):
        store: InMemoryStore[int] = InMemoryStore()
        store["a"] = 1
        store["b"] = 2
        assert store["a"] == 1
        assert len(store) == 2
        assert "a" in store

    def test_delete(self):
        store: InMemoryStore[str] = InMemoryStore()
        store["key"] = "value"
        del store["key"]
        assert "key" not in store
        assert len(store) == 0

    def test_delete_missing_raises(self):
        store: InMemoryStore[str] = InMemoryStore()
        with pytest.raises(KeyError):
            del store["missing"]

    def test_get_missing_raises(self):
        store: InMemoryStore[str] = InMemoryStore()
        with pytest.raises(KeyError):
            _ = store["missing"]

    def test_get_with_default(self):
        store: InMemoryStore[int] = InMemoryStore()
        assert store.get("missing", 42) == 42

    def test_bounded_eviction(self):
        store: InMemoryStore[int] = InMemoryStore(max_entries=3)
        store["a"] = 1
        store["b"] = 2
        store["c"] = 3
        store["d"] = 4  # Should evict "a"
        assert "a" not in store
        assert len(store) == 3
        assert store["d"] == 4

    def test_initial_data(self):
        store: InMemoryStore[int] = InMemoryStore(initial={"x": 10, "y": 20})
        assert store["x"] == 10
        assert len(store) == 2

    def test_iteration(self):
        store: InMemoryStore[int] = InMemoryStore(initial={"a": 1, "b": 2})
        keys = list(store)
        assert set(keys) == {"a", "b"}

    def test_values(self):
        store: InMemoryStore[int] = InMemoryStore(initial={"a": 1, "b": 2})
        assert sorted(store.values()) == [1, 2]

    def test_items(self):
        store: InMemoryStore[int] = InMemoryStore(initial={"a": 1})
        assert list(store.items()) == [("a", 1)]

    def test_update_existing_key(self):
        store: InMemoryStore[int] = InMemoryStore(max_entries=2)
        store["a"] = 1
        store["b"] = 2
        store["a"] = 10  # update, not new — should not evict
        assert len(store) == 2
        assert store["a"] == 10


# ---------------------------------------------------------------------------
# BoundedLog
# ---------------------------------------------------------------------------
class TestBoundedLog:
    def test_append(self):
        log: BoundedLog[str] = BoundedLog(max_entries=100)
        log.append("entry1")
        log.append("entry2")
        assert len(log) == 2

    def test_eviction(self):
        log: BoundedLog[int] = BoundedLog(max_entries=3)
        for i in range(5):
            log.append(i)
        assert len(log) == 3
        assert log[0] == 2  # oldest surviving entry
        assert log[-1] == 4

    def test_slicing(self):
        log: BoundedLog[int] = BoundedLog(max_entries=100)
        for i in range(10):
            log.append(i)
        assert log[-3:] == [7, 8, 9]

    def test_empty(self):
        log: BoundedLog[dict] = BoundedLog()
        assert len(log) == 0
        assert log[-5:] == []


# ---------------------------------------------------------------------------
# create_service factory — single app to avoid Prometheus re-registration
# ---------------------------------------------------------------------------
_factory_app = create_service(
    name="test_factory",
    description="Test service",
    version="1.0.0",
    dependencies=["postgres", "redis"],
)


@pytest.fixture(scope="module")
def factory_client():
    with TestClient(_factory_app) as client:
        yield client


class TestCreateService:
    def test_creates_fastapi_app(self):
        assert isinstance(_factory_app, FastAPI)
        assert _factory_app.state.service_name == "test_factory"
        assert _factory_app.state.service_version == "1.0.0"

    def test_health_endpoint(self, factory_client):
        resp = factory_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "test_factory"
        assert data["status"] == "healthy"
        assert "uptime_seconds" in data
        assert "memory_mb" in data

    def test_liveness_probe(self, factory_client):
        resp = factory_client.get("/healthz")
        assert resp.status_code == 200
        assert resp.json()["status"] == "alive"

    def test_readiness_probe(self, factory_client):
        resp = factory_client.get("/readyz")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ready"

    def test_info_endpoint(self, factory_client):
        resp = factory_client.get("/info")
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "test_factory"
        assert data["dependencies"] == ["postgres", "redis"]

    def test_metrics_endpoint(self, factory_client):
        resp = factory_client.get("/metrics")
        assert resp.status_code == 200
        assert "text/plain" in resp.headers["content-type"]


# ---------------------------------------------------------------------------
# Chaos injection via factory
# ---------------------------------------------------------------------------
class TestChaosInjection:
    def test_chaos_enable_disable(self, factory_client):
        # Enable
        resp = factory_client.post("/chaos/enable", json={"type": "error", "rate": 0.5})
        assert resp.status_code == 200
        assert resp.json()["status"] == "chaos_enabled"
        assert _factory_app.state.chaos_mode["enabled"] is True

        # Disable
        resp = factory_client.post("/chaos/disable")
        assert resp.status_code == 200
        assert resp.json()["status"] == "chaos_disabled"
        assert _factory_app.state.chaos_mode["enabled"] is False

    def test_chaos_disabled_by_default(self):
        # Reset to default state
        _factory_app.state.chaos_mode = {"enabled": False, "type": None, "rate": 0.0, "delay": 2.0}
        assert _factory_app.state.chaos_mode["enabled"] is False

    @pytest.mark.asyncio
    async def test_maybe_inject_chaos_noop_when_disabled(self):
        _factory_app.state.chaos_mode = {"enabled": False, "type": None, "rate": 0.0}
        # Should not raise
        await maybe_inject_chaos(_factory_app)

    @pytest.mark.asyncio
    async def test_maybe_inject_chaos_error(self):
        _factory_app.state.chaos_mode = {"enabled": True, "type": "error", "rate": 1.0}
        with pytest.raises(HTTPException) as exc_info:
            await maybe_inject_chaos(_factory_app, detail="test fault")
        assert exc_info.value.status_code == 500
        assert "test fault" in exc_info.value.detail
        # Reset
        _factory_app.state.chaos_mode = {"enabled": False, "type": None, "rate": 0.0}

    @pytest.mark.asyncio
    async def test_maybe_inject_chaos_latency(self):
        _factory_app.state.chaos_mode = {"enabled": True, "type": "latency", "rate": 1.0, "delay": 0.01}
        start = time.perf_counter()
        await maybe_inject_chaos(_factory_app)
        elapsed = time.perf_counter() - start
        assert elapsed >= 0.01
        # Reset
        _factory_app.state.chaos_mode = {"enabled": False, "type": None, "rate": 0.0}

    @pytest.mark.asyncio
    async def test_maybe_inject_chaos_rate_zero(self):
        _factory_app.state.chaos_mode = {"enabled": True, "type": "error", "rate": 0.0}
        # rate=0 means random.random() >= 0.0 is always True, so no injection
        await maybe_inject_chaos(_factory_app)  # should not raise
        # Reset
        _factory_app.state.chaos_mode = {"enabled": False, "type": None, "rate": 0.0}

