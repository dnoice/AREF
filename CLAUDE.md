# AREF — Development Guide

## Quick Reference

```bash
# Install
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=aref --cov=services

# Lint
ruff check .

# Type check
mypy aref/

# Start dashboard (local dev)
uvicorn aref.dashboard.app:app --port 8080

# Start full stack (Docker)
docker compose up --build
```

## Conventions

### Docstring Standard
All files **must** follow `docs/standards/DOCSTRING_STANDARDS.md`. Every file requires a metadata header with Title, File Name, Relative Path, Version, Date, Author, A.I. Acknowledgement, and Signature.

### Service Naming
Service files use `{service}_app.py` convention (e.g., `gateway_app.py`, `orders_app.py`).

### Engine Pattern
All pillar engines implement: `__init__()`, `async start()`, `async stop()`, `get_status() -> dict`.

### Singletons
Access via `get_X()` / `reset_X()` functions: `get_config()`, `get_event_bus()`, `get_metrics_engine()`, `get_circuit_breaker_registry()`.

### Event Bus Topics
Format: `"category.event_type"` (e.g., `"detection.alert_fired"`, `"recovery.recovery_resolved"`).

## Architecture

- `aref/core/` — Shared infrastructure (config, events, metrics, models, logging)
- `aref/detection/` — Pillar I: Early warning & anomaly detection
- `aref/absorption/` — Pillar II: Impact containment (circuit breakers, bulkheads, rate limiters)
- `aref/adaptation/` — Pillar III: Real-time reconfiguration (feature flags, traffic shifting, scaling)
- `aref/recovery/` — Pillar IV: Tiered service restoration (T0-T4)
- `aref/evolution/` — Pillar V: Post-incident learning
- `aref/maturity/` — CRS scoring & maturity assessment
- `aref/dashboard/` — FastAPI control plane + web UI
- `aref/cli/` — Click-based CLI
- `services/` — 5 FastAPI microservices + shared factory (`base.py`)
- `chaos/` — Fault injection & experiment runner
- `scripts/` — Demo script

## In-Memory Architecture
All state is in-memory. PostgreSQL and Redis are provisioned in Docker but not yet connected. Database persistence is a future phase.
