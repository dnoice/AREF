<div align="center">

# AREF — Adaptive Resilience Engineering Framework

**A comprehensive systems-level platform for infrastructure resilience, failure recovery, and operational continuity**

[![Version](https://img.shields.io/badge/version-2.0.0-blue.svg)](https://github.com/dnoice/AREF)
[![Python](https://img.shields.io/badge/python-3.11%2B-brightgreen.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-Apache%202.0-orange.svg)](LICENSE)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688.svg)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/docker-compose-2496ED.svg)](docker-compose.yml)
[![Tests](https://img.shields.io/badge/tests-pytest-brightgreen.svg)](tests/)

*Author: Dennis 'dnoice' Smaltz — digiSpace Technical Studio*

</div>

---

## Table of Contents

- [Overview](#overview)
- [The Five Pillars of Resilience](#the-five-pillars-of-resilience)
- [Architecture](#architecture)
- [Key Features](#key-features)
- [Tech Stack](#tech-stack)
- [Quick Start](#quick-start)
  - [Option 1 — Full Stack (Docker)](#option-1--full-stack-docker)
  - [Option 2 — Dashboard Only (Local)](#option-2--dashboard-only-local)
  - [Option 3 — Interactive Demo](#option-3--interactive-demo)
  - [Option 4 — CLI](#option-4--cli)
- [Installation](#installation)
- [Configuration](#configuration)
- [Microservices](#microservices)
- [Dashboard & API](#dashboard--api)
- [CLI Reference](#cli-reference)
- [Chaos Engineering](#chaos-engineering)
- [Composite Resilience Score (CRS)](#composite-resilience-score-crs)
- [Maturity Model](#maturity-model)
- [Runbooks](#runbooks)
- [Testing](#testing)
- [Project Structure](#project-structure)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

**AREF** (Adaptive Resilience Engineering Framework) is a production-grade reference implementation of a **self-healing distributed systems platform**. It operationalises the five engineering disciplines required to keep complex services reliable under failure conditions:

1. **Detect** anomalies early, before they cascade
2. **Absorb** the blast radius and contain the damage
3. **Adapt** dynamically by reconfiguring in real-time
4. **Recover** in a tiered, runbook-driven fashion
5. **Evolve** continuously through post-incident learning

AREF ships with a live control-plane dashboard, a rich CLI, five instrumented microservices, a chaos-injection engine, Prometheus/Grafana observability, and a complete test suite — everything needed to study, demo, and extend resilience engineering patterns.

> **Status:** Reference / Framework stage. All state is in-memory. PostgreSQL and Redis are provisioned in Docker but not yet wired to the application layer (planned future phase).

---

## The Five Pillars of Resilience

```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│  Pillar I   │  │  Pillar II  │  │  Pillar III │  │  Pillar IV  │  │  Pillar V   │
│  DETECTION  │→ │ ABSORPTION  │→ │ ADAPTATION  │→ │  RECOVERY   │→ │  EVOLUTION  │
│             │  │             │  │             │  │             │  │             │
│ Early       │  │ Impact      │  │ Real-time   │  │ Tiered      │  │ Post-       │
│ warning &   │  │ containment │  │ reconfig-   │  │ service     │  │ incident    │
│ anomaly     │  │ & blast     │  │ uration     │  │ restoration │  │ learning    │
│ detection   │  │ radius ctrl │  │             │  │ (T0 – T4)   │  │             │
└─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘
```

| Pillar | Purpose | Key Components |
|--------|---------|----------------|
| **I — Detection** | Identify failures before they become outages | Threshold detector, statistical anomaly detector (Z-score), synthetic probing, SLI/SLO tracking |
| **II — Absorption** | Contain blast radius and prevent cascades | Circuit breaker (3-state FSM), bulkhead isolation, token-bucket rate limiter, 4-tier graceful degradation, blast-radius graph |
| **III — Adaptation** | Reconfigure the system in real-time | Feature flags, weighted traffic shifting, horizontal auto-scaler, 6-step decision tree |
| **IV — Recovery** | Restore service in a structured, time-boxed way | Tiered runbook executor (T0–T4), YAML runbooks, incident commander workflow |
| **V — Evolution** | Turn every incident into a system improvement | Automated post-incident reviews, action-item tracker, pattern matcher, knowledge base |

---

## Architecture

```
                          ┌─────────────────────────────────┐
                          │   AREF Dashboard (port 8080)    │
                          │   FastAPI + SPA Web UI          │
                          │   REST API / Control Plane      │
                          └────────────┬────────────────────┘
                                       │ events / polling
              ┌────────────────────────▼────────────────────────────┐
              │              AREF Engine Core                        │
              │  ┌──────────┐ ┌──────────┐ ┌──────────┐            │
              │  │Detection │ │Absorption│ │Adaptation│            │
              │  │ Engine   │ │ Engine   │ │ Engine   │            │
              │  └──────────┘ └──────────┘ └──────────┘            │
              │  ┌──────────┐ ┌──────────┐ ┌──────────┐            │
              │  │Recovery  │ │Evolution │ │ Maturity │            │
              │  │ Engine   │ │ Engine   │ │ Assessor │            │
              │  └──────────┘ └──────────┘ └──────────┘            │
              │              Event Bus (pub/sub)                     │
              └───────────────────┬─────────────────────────────────┘
                                  │ HTTP / health checks
        ┌─────────────────────────▼──────────────────────────────────┐
        │                   Microservice Layer                        │
        │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐ │
        │  │ Gateway  │ │  Orders  │ │ Payments │ │  Inventory   │ │
        │  │ :8000    │ │  :8001   │ │  :8002   │ │    :8003     │ │
        │  └──────────┘ └──────────┘ └──────────┘ └──────────────┘ │
        │                      ┌──────────────────┐                  │
        │                      │  Notifications   │                  │
        │                      │     :8004        │                  │
        │                      └──────────────────┘                  │
        └────────────────────────────────────────────────────────────┘
                                  │
        ┌─────────────────────────▼──────────────────────────────────┐
        │                 Observability Layer                         │
        │         Prometheus :9090  ·  Grafana :3000                 │
        └────────────────────────────────────────────────────────────┘
```

### Event-Driven Communication

All engines communicate through an **async in-process event bus** using a `"category.event_type"` topic format:

| Topic | Published by |
|-------|-------------|
| `detection.alert_fired` | Detection Engine |
| `absorption.circuit_breaker_opened` | Absorption Engine |
| `adaptation.adaptation_executed` | Adaptation Engine |
| `recovery.recovery_started` | Recovery Engine |
| `recovery.recovery_resolved` | Recovery Engine |
| `evolution.post_incident_review_generated` | Evolution Engine |

Engines can subscribe using wildcards: `"detection.*"` or `"*"` for all events.

---

## Key Features

- **Five-Pillar Resilience Framework** — A complete, end-to-end incident lifecycle implemented in code
- **Composite Resilience Score (CRS)** — A single weighted metric (0–5) reflecting overall system resilience across configurable risk profiles
- **Five-Level Maturity Model** — Per-pillar gap analysis from *Reactive* to *Optimizing*
- **Live Dashboard** — Single-page control plane with real-time CRS, pillar health, incident timeline, and chaos controls
- **Rich CLI** — Full `aref` command-line interface for status, maturity, chaos, and timeline
- **Chaos Engineering Engine** — Five pre-defined fault-injection experiments with automatic rollback
- **Runbook-Driven Recovery** — YAML-defined, version-controlled runbooks with T0–T4 tiering
- **Prometheus + Grafana** — Out-of-the-box metrics, scrape configs, and Grafana provisioning
- **Five Instrumented Microservices** — Gateway + Orders + Payments + Inventory + Notifications with shared factory
- **Structured Logging** — structlog throughout, with correlation IDs
- **Interactive Demo** — End-to-end Rich terminal demo with scenario walkthroughs
- **Full Test Suite** — Unit and integration tests covering the complete incident lifecycle

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11+ |
| Web Framework | FastAPI 0.110+ |
| ASGI Server | Uvicorn |
| Data Validation | Pydantic v2, pydantic-settings |
| CLI | Click + Rich |
| Metrics | Prometheus Client, prometheus-fastapi-instrumentator |
| Anomaly Detection | NumPy (Z-score, statistical baseline) |
| Logging | structlog |
| Runbooks | PyYAML |
| HTTP Client | HTTPX |
| Containerisation | Docker, Docker Compose |
| Observability | Prometheus, Grafana |
| Database (provisioned) | PostgreSQL 16 |
| Cache (provisioned) | Redis 7 |
| Build | Hatchling |
| Test | pytest, pytest-asyncio, pytest-cov |
| Lint / Format | Ruff |
| Type Check | mypy (strict) |

---

## Quick Start

### Option 1 — Full Stack (Docker)

The fastest way to run everything — five microservices, the AREF control plane, Prometheus, and Grafana:

```bash
git clone https://github.com/dnoice/AREF.git
cd AREF

# (Optional) copy and customise environment config
cp .env.example .env

docker compose up --build
```

| Service | URL |
|---------|-----|
| AREF Dashboard | http://localhost:8080 |
| API Gateway | http://localhost:8000 |
| Orders Service | http://localhost:8001 |
| Payments Service | http://localhost:8002 |
| Inventory Service | http://localhost:8003 |
| Notifications Service | http://localhost:8004 |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 (admin / aref) |

### Option 2 — Dashboard Only (Local)

Run just the AREF control plane locally without Docker:

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Start the dashboard
uvicorn aref.dashboard.app:app --port 8080 --reload
```

Open http://localhost:8080 in your browser.

### Option 3 — Interactive Demo

An end-to-end Rich terminal walkthrough of the full incident lifecycle:

```bash
pip install -e ".[dev]"

# Run the full interactive demo
python -m scripts.demo

# Run a specific experiment directly
python -m scripts.demo --experiment payment_provider_failure
```

### Option 4 — CLI

```bash
pip install -e ".[dev]"

aref status                              # Platform overview & CRS
aref pillars                             # Per-pillar health & scores
aref maturity                            # Maturity assessment & gap analysis
aref timeline                            # Recent event history
aref chaos list                          # Available chaos experiments
aref chaos run payment_provider_failure  # Inject a fault
aref serve                               # Start dashboard from CLI
```

---

## Installation

**Prerequisites:** Python 3.11+, pip

```bash
# Clone the repository
git clone https://github.com/dnoice/AREF.git
cd AREF

# Install runtime dependencies only
pip install -e .

# Install with developer tooling (tests, lint, type-check)
pip install -e ".[dev]"
```

---

## Configuration

All configuration is driven by environment variables (or a `.env` file). Copy the template to get started:

```bash
cp .env.example .env
```

### General Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `AREF_ENVIRONMENT` | `development` | Set to `docker` for container hostnames |
| `AREF_DEBUG` | `true` | Enable debug mode |
| `AREF_LOG_LEVEL` | `INFO` | Log verbosity |
| `AREF_RISK_PROFILE` | `balanced` | CRS weighting profile (see [CRS section](#composite-resilience-score-crs)) |
| `AREF_API_HOST` | `0.0.0.0` | API bind address |
| `AREF_API_PORT` | `8000` | API listen port |
| `AREF_DASHBOARD_PORT` | `8080` | Dashboard listen port |

### Pillar-Specific Settings (selected)

| Variable | Default | Description |
|----------|---------|-------------|
| `AREF_DETECTION_MTTD_TARGET_SECONDS` | `300` | MTTD target (< 5 min) |
| `AREF_ABSORPTION_CIRCUIT_BREAKER_FAILURE_THRESHOLD` | `5` | Failures before circuit opens |
| `AREF_ABSORPTION_CIRCUIT_BREAKER_RECOVERY_TIMEOUT` | `30` | Seconds before half-open |
| `AREF_ABSORPTION_RATE_LIMIT_REQUESTS_PER_SECOND` | `100` | Token bucket rate limit |
| `AREF_ADAPTATION_ADAPTATION_WINDOW_SECONDS` | `120` | Window before escalating to recovery |
| `AREF_RECOVERY_MTTR_TARGET_SECONDS` | `900` | MTTR target (< 15 min) |
| `AREF_EVOLUTION_ACTION_COMPLETION_RATE_TARGET` | `85` | Target action completion % |

See [`.env.example`](.env.example) for the full list of 60+ variables covering all five pillars, database, Redis, and Grafana.

---

## Microservices

All five services are built through the shared `services/base.py` factory (`create_service()`), which automatically provides:

- Prometheus instrumentation (`/metrics`)
- Health and readiness probes (`/health`, `/readyz`)
- Service info endpoint (`/info`)
- Correlation ID propagation
- Structured logging
- CORS middleware

| Service | Port | Responsibility |
|---------|------|---------------|
| **Gateway** | 8000 | Request routing, retry logic, circuit-breaker awareness, order pipeline orchestration |
| **Orders** | 8001 | Order lifecycle state machine, payment callbacks, inventory coordination, audit trail |
| **Payments** | 8002 | Payment provider integration, failure simulation, queued payments |
| **Inventory** | 8003 | Stock management, reservation, degradation scenarios |
| **Notifications** | 8004 | Queue-based notification dispatch |

---

## Dashboard & API

The AREF Dashboard is a **FastAPI** application (`aref/dashboard/app.py`) that serves:

- A **single-page web application** (`/`) with six tabs: Overview, Pillars, Services, Metrics, Chaos, and Timeline
- A **REST API** under `/api/v1/` with four route groups:

| Route Group | Path Prefix | Description |
|-------------|------------|-------------|
| Status | `/api/v1/status/` | Platform status, service health, incident list |
| Pillars | `/api/v1/pillars/` | Per-pillar status, scores, and active alerts |
| Metrics | `/api/v1/metrics/` | CRS, MTTD, MTTR, pillar scores |
| Chaos | `/api/v1/chaos/` | List experiments, inject faults, rollback |

The dashboard polls all five microservices every 10 seconds and updates the UI in real-time.

---

## CLI Reference

The `aref` CLI is built with Click and Rich:

```
Usage: aref [OPTIONS] COMMAND [ARGS]...

Commands:
  status    Display platform status and overall CRS score
  pillars   Show per-pillar health, scores, and active alerts
  maturity  Run maturity assessment and gap analysis
  timeline  Display recent event history from the event bus
  chaos     Manage and run chaos experiments
  serve     Start the AREF dashboard server
```

```bash
# View platform status with CRS
aref status

# Detailed pillar breakdown
aref pillars

# Maturity assessment across all five pillars
aref maturity

# Recent event timeline (last 20 events)
aref timeline --limit 20

# List available chaos experiments
aref chaos list

# Run a specific experiment
aref chaos run cascading_failure

# Start the dashboard (alternative to uvicorn)
aref serve --port 8080
```

---

## Chaos Engineering

AREF ships with a **FaultInjector** (`chaos/injector.py`) and five pre-defined experiments (`chaos/experiments.py`):

| Experiment | Target | Fault Type | Description |
|------------|--------|-----------|-------------|
| `payment_provider_failure` | Payments | Error injection | Simulates a payment provider outage |
| `order_service_latency` | Orders | Latency injection | Adds artificial latency to order processing |
| `inventory_degradation` | Inventory | Error rate + degradation | Triggers graceful degradation mode |
| `notification_overload` | Notifications | Load spike | Floods the notification queue |
| `cascading_failure` | Multiple | Multi-service | Simulates a cascading cross-service failure |

All experiments include **automatic rollback** — the injector restores the original service behaviour when the experiment concludes or times out.

### Running Chaos via the API

```bash
# List experiments
GET /api/v1/chaos/experiments

# Start an experiment
POST /api/v1/chaos/experiments/{experiment_id}/start

# Rollback (stop experiment)
POST /api/v1/chaos/experiments/{experiment_id}/stop
```

---

## Composite Resilience Score (CRS)

The **CRS** is a single weighted metric in the range **0.0 – 5.0** that reflects overall system resilience. The weight of each pillar is determined by the active **risk profile**:

| Pillar | Availability Critical | Data Integrity Critical | Balanced | Innovation Heavy |
|--------|----------------------|------------------------|---------|----------------|
| Detection | 30% | 20% | 20% | 15% |
| Absorption | 25% | 20% | 20% | 15% |
| Adaptation | 20% | 15% | 20% | 25% |
| Recovery | 15% | 30% | 20% | 15% |
| Evolution | 10% | 15% | 20% | 30% |

Set the risk profile via `AREF_RISK_PROFILE` environment variable (options: `balanced`, `availability_critical`, `data_integrity_critical`, `innovation_heavy`).

**Formula:**
```
CRS = Σ (pillar_score × weight)  for each pillar in {I, II, III, IV, V}
```

---

## Maturity Model

Each pillar is assessed independently on a **five-level maturity scale**:

| Level | Name | Characteristics |
|-------|------|----------------|
| **1** | Reactive | Ad-hoc responses, no documented processes |
| **2** | Managed | Repeatable processes, basic monitoring in place |
| **3** | Defined | Documented procedures, standard tooling adopted |
| **4** | Measured | Quantified metrics, targets tracked and met |
| **5** | Optimizing | Continuous improvement, full automation, feedback loops |

The **MaturityAssessor** (`aref/maturity/model.py`) calculates a score for each pillar, identifies gaps, and generates prioritised improvement recommendations. Access via `aref maturity` or the Dashboard *Maturity* tab.

---

## Runbooks

Recovery runbooks are **YAML-defined** files stored in `runbooks/` and executed by the `RunbookExecutor` (`aref/recovery/runbooks.py`).

### Runbook Structure

```yaml
runbooks:
  - name: payment_t0_stabilize
    service: payments
    tier: 0               # T0 = fully automated, 0–5 minutes
    version: "1.0.0"
    description: "Emergency stabilization for payment provider outage"
    steps:
      - order: 1
        action: detect_payment_failures
        automated: true
        timeout_seconds: 10
      - order: 2
        action: open_circuit_breaker
        automated: true
        timeout_seconds: 5
      - order: 3
        action: switch_provider
        automated: true
        timeout_seconds: 10
        escalation: "Page on-call if backup provider also fails"
```

### Recovery Tiers

| Tier | Time Window | Automation | Owner |
|------|-------------|-----------|-------|
| **T0** | 0 – 5 min | Fully automated | System |
| **T1** | 5 – 15 min | Mostly automated | Incident Commander |
| **T2** | 15 – 60 min | Semi-automated | Engineering team |
| **T3** | 1 – 4 hours | Manual with tooling | Senior engineers |
| **T4** | 1 – 2 weeks | Process-driven | Leadership + Engineering |

---

## Testing

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run all tests
pytest tests/ -v

# Run with coverage report
pytest tests/ -v --cov=aref --cov=services

# Run only unit tests
pytest tests/unit/ -v

# Run only integration tests
pytest tests/integration/ -v
```

### Test Coverage

| Suite | File | What's Tested |
|-------|------|--------------|
| Unit | `tests/unit/test_core.py` | Config, event bus, metrics, models |
| Unit | `tests/unit/test_pillars.py` | Circuit breaker FSM, feature flags, recovery tiers |
| Integration | `tests/integration/test_full_pipeline.py` | Complete incident lifecycle: detection → absorption → adaptation → recovery → evolution |

### Linting & Type Checking

```bash
# Lint with Ruff
ruff check .

# Type check with mypy (strict mode)
mypy aref/
```

---

## Project Structure

```
AREF/
├── aref/                          # Core AREF framework package
│   ├── core/                      # Shared infrastructure
│   │   ├── config.py              # Pydantic-settings configuration (env-driven)
│   │   ├── events.py              # Async event bus (pub/sub + history)
│   │   ├── metrics.py             # Prometheus metrics + CRS formula engine
│   │   ├── models.py              # Domain models (Incident, ActionItem, …)
│   │   └── logging.py             # structlog setup
│   ├── detection/                 # Pillar I — Early warning & anomaly detection
│   │   ├── engine.py              # DetectionEngine orchestrator
│   │   ├── threshold.py           # Metric threshold detection
│   │   ├── anomaly.py             # Statistical anomaly detection (Z-score)
│   │   ├── synthetic.py           # Active HTTP synthetic probing
│   │   └── sli_tracker.py         # SLI/SLO tracking + error budget
│   ├── absorption/                # Pillar II — Impact containment
│   │   ├── circuit_breaker.py     # 3-state circuit breaker + registry
│   │   ├── bulkhead.py            # Semaphore-based concurrency isolation
│   │   ├── rate_limiter.py        # Token bucket rate limiting
│   │   ├── blast_radius.py        # Dependency graph + blast radius analysis
│   │   └── degradation.py         # 4-tier graceful degradation
│   ├── adaptation/                # Pillar III — Real-time reconfiguration
│   │   ├── engine.py              # AdaptationEngine orchestrator
│   │   ├── decision_tree.py       # 6-step adaptation decision tree
│   │   ├── feature_flags.py       # Feature flag manager
│   │   ├── traffic_shifter.py     # Weighted route redistribution
│   │   └── scaler.py              # Simulated horizontal auto-scaler
│   ├── recovery/                  # Pillar IV — Tiered service restoration
│   │   ├── engine.py              # RecoveryEngine (T0–T4 orchestration)
│   │   └── runbooks.py            # YAML runbook executor
│   ├── evolution/                 # Pillar V — Post-incident learning
│   │   ├── engine.py              # EvolutionEngine orchestrator
│   │   ├── post_incident.py       # Automated PIR generator
│   │   ├── tracker.py             # Action item tracker
│   │   ├── patterns.py            # Incident pattern matcher
│   │   └── knowledge_base.py      # Lessons-learned repository
│   ├── maturity/                  # Maturity assessment & CRS scoring
│   │   └── model.py               # MaturityAssessor (L1–L5, gap analysis)
│   ├── dashboard/                 # Control plane — FastAPI + SPA
│   │   ├── app.py                 # Main FastAPI application
│   │   ├── routes/                # API route handlers (status, pillars, metrics, chaos)
│   │   ├── templates/index.html   # Single-page application (6 tabs)
│   │   └── static/                # CSS, JS, SVG assets
│   └── cli/
│       └── main.py                # Click CLI (status, pillars, maturity, chaos, timeline, serve)
│
├── services/                      # Five FastAPI microservices
│   ├── base.py                    # Shared service factory (health, metrics, CORS, logging)
│   ├── gateway/gateway_app.py     # API Gateway (port 8000)
│   ├── orders/orders_app.py       # Orders service (port 8001)
│   ├── payments/payments_app.py   # Payments service (port 8002)
│   ├── inventory/inventory_app.py # Inventory service (port 8003)
│   └── notifications/notifications_app.py  # Notifications service (port 8004)
│
├── chaos/                         # Fault injection & experiments
│   ├── injector.py                # FaultInjector with auto-rollback
│   └── experiments.py             # 5 pre-defined chaos experiments
│
├── scripts/
│   └── demo.py                    # Interactive end-to-end demo (Rich UI)
│
├── tests/
│   ├── unit/
│   │   ├── test_core.py           # Core infrastructure tests
│   │   └── test_pillars.py        # Pillar unit tests
│   └── integration/
│       └── test_full_pipeline.py  # Full incident lifecycle integration test
│
├── runbooks/
│   └── payment_failure.yml        # T0 & T1 runbooks for payment outage
│
├── config/
│   ├── prometheus.yml             # Prometheus scrape config
│   └── grafana/provisioning/      # Grafana dashboard provisioning
│
├── docs/
│   ├── assets/                    # Diagrams and framework documents
│   ├── blueprint.pdf              # Architectural blueprint
│   └── standards/
│       └── DOCSTRING_STANDARDS.md # Mandatory file header format
│
├── docker-compose.yml             # Full stack orchestration (8 services)
├── Dockerfile                     # Python 3.11-slim container image
├── pyproject.toml                 # Project metadata, dependencies, tool config
├── .env.example                   # Environment variable template
└── LICENSE                        # Apache 2.0
```

---

## Contributing

1. Fork the repository and create a feature branch
2. Follow the [Docstring Standards](docs/standards/DOCSTRING_STANDARDS.md) — every file requires the mandatory metadata header
3. Ensure your code passes linting and type checks:
   ```bash
   ruff check .
   mypy aref/
   ```
4. Add or update tests to cover your changes:
   ```bash
   pytest tests/ -v --cov=aref --cov=services
   ```
5. Open a pull request with a clear description of your changes

### Development Notes

- **Singletons** are accessed via `get_X()` / `reset_X()` functions (e.g. `get_config()`, `get_event_bus()`, `get_metrics_engine()`)
- **Engine pattern** — all pillar engines implement `async start()`, `async stop()`, and `get_status() -> dict`
- **Service files** follow the `{service}_app.py` naming convention
- **Event bus topics** use the `"category.event_type"` format

---

## License

Copyright © 2025 Dennis 'dnoice' Smaltz — digiSpace Technical Studio

Licensed under the [Apache License, Version 2.0](LICENSE).

---

<div align="center">

*Built with care for the craft of resilience engineering.*

</div>
