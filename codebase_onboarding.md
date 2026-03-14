# AREF Codebase Onboarding

**Adaptive Resilience Engineering Framework v2.0.0**
Author: Dennis 'dnoice' Smaltz | digiSpace Technical Studio

---

## 1. Project Structure

```tree
aref/
| -- Dockerfile                              # Python 3.11-slim, pip install ., default uvicorn CMD
| -- docker-compose.yml                      # Full stack: 5 services + dashboard + postgres/redis/prometheus/grafana
| -- pyproject.toml                          # Hatchling build, all dependencies, CLI entrypoints
| -- README.md                               # Stub (single heading)
| -- .dockerignore
| -- .hintrc
|
| -- aref/                                   # Core AREF framework package
|   | -- __init__.py                         # v2.0.0, package root
|   |
|   | -- core/                               # Shared infrastructure
|   |   | -- __init__.py
|   |   | -- config.py                       # Pydantic-settings config (env-driven, per-pillar)
|   |   | -- events.py                       # Async in-process event bus (pub/sub + history)
|   |   | -- metrics.py                      # Prometheus metrics + AREF formula engine (MTTD/MTTR/CRS)
|   |   | -- models.py                       # Domain objects: Incident, ActionItem, ServiceInfo, HealthCheck
|   |   | -- logging.py                      # structlog configuration
|   |
|   | -- detection/                          # Pillar I: Early warning & anomaly identification
|   |   | -- __init__.py
|   |   | -- engine.py                       # DetectionEngine — orchestrates all detectors, alert lifecycle
|   |   | -- anomaly.py                      # Z-score + Isolation Forest anomaly detection
|   |   | -- threshold.py                    # ThresholdDetector — metric > threshold with consecutive confirmation
|   |   | -- synthetic.py                    # SyntheticProber — active HTTP health checks
|   |   | -- sli_tracker.py                  # SLI/SLO tracking + error budget computation
|   |
|   | -- absorption/                         # Pillar II: Impact containment & graceful degradation
|   |   | -- __init__.py
|   |   | -- circuit_breaker.py              # CircuitBreaker + CircuitBreakerRegistry (singleton)
|   |   | -- bulkhead.py                     # Semaphore-based concurrency limits per partition
|   |   | -- rate_limiter.py                 # Token bucket rate limiting
|   |   | -- blast_radius.py                 # Dependency graph + blast radius analysis
|   |   | -- degradation.py                  # 4-tier graceful degradation (Full/Reduced/Minimal/Emergency)
|   |
|   | -- adaptation/                         # Pillar III: Real-time reconfiguration
|   |   | -- __init__.py
|   |   | -- engine.py                       # AdaptationEngine — subscribes to alerts, executes strategies
|   |   | -- decision_tree.py                # 6-step decision tree: classify anomaly -> select strategy
|   |   | -- feature_flags.py               # FeatureFlagManager — toggle features, shed non-critical load
|   |   | -- traffic_shifter.py             # TrafficShifter — weighted route redistribution
|   |   | -- scaler.py                       # AutoScaler — simulated horizontal scaling
|   |
|   | -- recovery/                           # Pillar IV: Service restoration
|   |   | -- __init__.py
|   |   | -- engine.py                       # RecoveryEngine — tiered T0-T4 recovery orchestration
|   |   | -- runbooks.py                     # RunbookExecutor — YAML-loadable, step-by-step runbooks
|   |
|   | -- evolution/                          # Pillar V: Post-incident learning
|   |   | -- __init__.py
|   |   | -- engine.py                       # EvolutionEngine — auto-generates reviews on recovery_resolved
|   |   | -- post_incident.py                # PostIncidentReviewGenerator — 6-step structured reviews
|   |   | -- tracker.py                      # ActionTracker — action items to completion
|   |   | -- patterns.py                     # PatternMatcher — incident recurrence detection
|   |   | -- knowledge_base.py               # KnowledgeBase — incident data + lessons repository
|   |
|   | -- maturity/                           # Maturity assessment + CRS scoring
|   |   | -- __init__.py
|   |   | -- model.py                        # MaturityAssessor — L1-L5 per pillar, gap analysis, CRS
|   |
|   | -- dashboard/                          # Control Plane: FastAPI app + web UI
|   |   | -- __init__.py
|   |   | -- app.py                          # 1176 lines — API + lifespan wiring for all engines
|   |   | -- templates/
|   |   |   | -- index.html                  # 1229 lines — SPA dashboard (6 tabs)
|   |   | -- static/
|   |       | -- css/dashboard.css           # 2149 lines — full dashboard styling
|   |       | -- js/dashboard.js             # 2758 lines — client-side polling, charts, nav
|   |       | -- svg/icons.svg               # 109 lines — SVG icon sprite
|   |
|   | -- cli/                                # Rich terminal CLI
|       | -- __init__.py
|       | -- main.py                         # Click commands: status, pillars, maturity, chaos, timeline, serve
|
| -- chaos/                                  # Chaos engineering (top-level, not inside aref/)
|   | -- __init__.py
|   | -- injector.py                         # FaultInjector — latency/error/crash injection + auto-rollback
|   | -- experiments.py                      # 5 pre-defined experiments + ExperimentRunner
|
| -- services/                               # Microservice stack (FastAPI apps)
|   | -- __init__.py
|   | -- base.py                             # create_service() factory: health, readyz, info, metrics, CORS
|   | -- gateway/
|   |   | -- __init__.py
|   |   | -- gateway_app.py                  # API Gateway: routing, retries, circuit awareness, order pipeline
|   | -- orders/
|   |   | -- __init__.py
|   |   | -- orders_app.py                   # Order lifecycle state machine, audit trail
|   | -- payments/
|   |   | -- __init__.py
|   |   | -- payments_app.py                 # Multi-provider payments, auto-failover, refunds, settlement
|   | -- inventory/
|   |   | -- __init__.py
|   |   | -- inventory_app.py                # Stock management, reservations with TTL, replenishment
|   | -- notifications/
|       | -- __init__.py
|       | -- notifications_app.py            # Multi-channel dispatch, priority shedding, retry backoff
|
| -- scripts/
|   | -- __init__.py
|   | -- demo.py                             # 700 lines — 12-step Rich terminal demo with CLI args
|
| -- tests/
|   | -- __init__.py
|   | -- unit/
|   |   | -- __init__.py
|   |   | -- test_core.py                    # Config, EventBus, MetricsEngine, Models (4 test classes)
|   |   | -- test_pillars.py                 # All 5 pillars + maturity (10 test classes)
|   | -- integration/
|       | -- __init__.py
|       | -- test_full_pipeline.py           # Full D-A-A-R-E pipeline + event correlation (2 tests)
|
| -- config/
|   | -- prometheus.yml                      # Scrape config for all 6 services at /metrics
|   | -- grafana/
|       | -- provisioning/
|           | -- datasources/
|               | -- prometheus.yml          # Prometheus as default Grafana datasource
|
| -- runbooks/
|   | -- payment_failure.yml                 # T0 + T1 runbook for payment provider outage (YAML)
|
| -- docs/
    | -- blueprint.pdf                       # AREF Framework blueprint document
    | -- assets/
        | -- AREF_Framework_v2.0.0.docx
        | -- five-pillars.jpg
        | -- pillar-3.jpg
        | -- roadmap.jpg
        | -- safety.jpg
    | -- standards/
        | -- DOCSTRING_STANDARDS.md          # ALWAYS ADHERE TO THIS STANDARD FOR ALL FILES
```

### Total: ~82 source files, ~39 directories

---

## 2. Module Responsibility Map

| Module | Owns |
| -------- | ------ |
| `aref/core/` | Config (pydantic-settings), event bus (pub/sub + history), Prometheus metrics registry, AREF formula engine (MTTD/MTTR/CRS/availability/error budget), domain models (Incident, ActionItem, HealthCheck), structlog setup |
| `aref/detection/` | 4 detection classes: threshold-based (metric > threshold with consecutive confirmation), anomaly (Z-score + Isolation Forest), synthetic probing (active HTTP health checks), SLI/SLO tracking + error budget computation. Alert lifecycle (fire/ack/resolve), fatigue monitoring |
| `aref/absorption/` | Circuit breakers (CLOSED/HALF_OPEN/OPEN state machine + singleton registry), bulkheads (semaphore concurrency limits), token bucket rate limiters, blast radius analyzer (BFS dependency graph traversal + containment %), 4-tier graceful degradation manager |
| `aref/adaptation/` | 6-step decision tree (classify anomaly -> select minimum-impact strategy), feature flag manager (shed non-critical load), traffic shifter (weighted route redistribution), auto-scaler (simulated horizontal scaling). Subscribes to detection alerts + circuit breaker events |
| `aref/recovery/` | Tiered recovery engine (T0-T4 automatic escalation), runbook executor (YAML-loadable step-by-step procedures with role/timeout/escalation), T0/T1 fully automated, T2+ requires human coordination |
| `aref/evolution/` | Post-incident review generator (6-step blameless process), action item tracker (target: >85% completion, >8/quarter), pattern matcher (recurrence detection, target: <10%), knowledge base (lessons + incident data store) |
| `aref/maturity/` | L1-L5 maturity assessor (Reactive through Optimizing), per-pillar criteria evaluation with lambda checks, gap analysis, CRS scoring across all 4 risk profiles |
| `aref/dashboard/` | FastAPI control plane (1176 lines), lifespan wiring for all 5 engines, REST API (19 endpoints), web SPA dashboard (6 tabs: Overview, Detection, Absorption, Adaptation, Services, Timeline), Prometheus /metrics export |
| `aref/cli/` | Click-based Rich terminal CLI: `aref status`, `aref pillars`, `aref maturity`, `aref chaos [experiment]`, `aref chaos-stop`, `aref timeline`, `aref serve` |
| `chaos/` | FaultInjector (latency/error/crash/timeout injection with safety bounds: max 90% rate, max 5min duration, auto-rollback), 5 pre-defined experiments, ExperimentRunner |
| `services/` | 5 FastAPI microservices + shared factory. Gateway routes to downstream services with retries/circuit awareness. Each service has /health, /healthz, /readyz, /info, /metrics, /chaos/enable, /chaos/disable |
| `services/base.py` | `create_service()` factory: request/error counting, response time headers, X-Service/X-Request-ID headers, /health (uptime, requests, errors, memory), /healthz (liveness), /readyz (readiness), /info (metadata), CORS, unhandled exception middleware |
| `scripts/` | `demo.py` — 12-step end-to-end demo: preflight -> baseline CRS -> traffic -> deep health -> chaos inject -> incident traffic -> pillar deep-dive -> timeline -> chaos rollback -> recovery traffic -> final CRS -> comparison |
| `tests/` | Unit tests for core (config, events, metrics, models) + all 5 pillars + maturity (14 test classes). Integration tests for full D-A-A-R-E pipeline + event correlation |
| `config/` | Prometheus scrape config (10s interval, all 6 services), Grafana datasource provisioning |
| `runbooks/` | YAML runbook definitions (payment_failure.yml has T0 + T1 procedures) |

---

## 3. Configuration Architecture

### Source: `aref/core/config.py`

Uses **pydantic-settings** with `SettingsConfigDict(env_prefix="AREF_...")`. Configuration cascades:

1. **Environment variables** (highest priority) — prefix-based:
   - `AREF_ENVIRONMENT`, `AREF_DEBUG`, `AREF_LOG_LEVEL`, `AREF_RISK_PROFILE`
   - `AREF_DB_HOST`, `AREF_DB_PORT`, `AREF_DB_NAME`, `AREF_DB_USER`, `AREF_DB_PASSWORD`
   - `AREF_REDIS_HOST`, `AREF_REDIS_PORT`
   - `AREF_DETECTION_MTTD_TARGET_SECONDS`, `AREF_DETECTION_THRESHOLD_CHECK_INTERVAL`, ...
   - `AREF_ABSORPTION_CIRCUIT_BREAKER_FAILURE_THRESHOLD`, ...
   - `AREF_ADAPTATION_LATENCY_TARGET_SECONDS`, ...
   - `AREF_RECOVERY_MTTR_TARGET_SECONDS`, `AREF_RECOVERY_T0_TARGET_SECONDS`, ...
   - `AREF_EVOLUTION_IMPROVEMENT_VELOCITY_TARGET`, ...
2. **Hardcoded defaults** (fallback) — all values have sensible defaults aligned with blueprint
3. No TOML/YAML config files used — pure env vars + defaults

### Key Config Sections

| Section | Class | Key Fields |
| --------- | ------- | ------------ |
| Root | `AREFConfig` | `environment`, `debug`, `log_level`, `risk_profile` (4 profiles), `api_host`, `api_port`, `dashboard_port` |
| Database | `DatabaseConfig` | PostgreSQL DSN builder, pool_min=2, pool_max=10 |
| Redis | `RedisConfig` | Redis URL builder, db=0 |
| Detection | `DetectionConfig` | `mttd_target_seconds=300`, `threshold_check_interval=10`, `anomaly_check_interval=30`, `synthetic_probe_interval=15`, `alert_fatigue_max_per_week=50`, `alert_to_action_ratio=3.0` |
| Absorption | `AbsorptionConfig` | `blast_radius_target_pct=95`, `circuit_breaker_failure_threshold=5`, `circuit_breaker_recovery_timeout=30`, `bulkhead_max_concurrent=50`, `rate_limit_requests_per_second=100` |
| Adaptation | `AdaptationConfig` | `latency_target_seconds=30`, `scale_up_cpu_threshold=80`, `feature_flag_error_budget_trigger=0.5`, `adaptation_window_seconds=120` |
| Recovery | `RecoveryConfig` | `mttr_target_seconds=900`, `t0=300s`, `t1=900s`, `t2=3600s`, `t3=14400s`, `t4=14 days`, `runbook_drill_interval_days=90` |
| Evolution | `EvolutionConfig` | `improvement_velocity_target=8`, `action_completion_rate_target=85`, `recurrence_rate_target=10`, `post_incident_review_deadline_hours=72` |

### Risk Profiles (CRS Weight Profiles)

From blueprint Section 6.3:

| Profile | Detection | Absorption | Adaptation | Recovery | Evolution |
| --------- | ----------- | ----------- | ------------ | ---------- | ----------- |
| availability_critical | 0.30 | 0.25 | 0.20 | 0.15 | 0.10 |
| data_integrity_critical | 0.20 | 0.20 | 0.15 | 0.30 | 0.15 |
| **balanced** (default) | 0.20 | 0.20 | 0.20 | 0.20 | 0.20 |
| innovation_heavy | 0.15 | 0.15 | 0.25 | 0.15 | 0.30 |

### Monitoring Config

- **`config/prometheus.yml`**: Scrapes all 6 services at their `/metrics` endpoint every 10s: dashboard:8080, gateway:8000, orders:8001, payments:8002, inventory:8003, notifications:8004
- **`config/grafana/provisioning/datasources/prometheus.yml`**: Auto-provisions Prometheus as default datasource at `http://prometheus:9090`

---

## 4. Data Flow / Wiring Summary

### Lifespan Bootstrap (dashboard/app.py)

On startup, `lifespan()` wires everything:

```text
1. Initialize all 5 engines (Detection, Adaptation, Recovery, Evolution) + Chaos Injector
2. Start engine event loop subscriptions:
   - Adaptation subscribes to: detection.alert_fired, absorption.circuit_breaker_opened
   - Recovery subscribes to:   adaptation.escalate_to_recovery, detection.alert_fired (EMERGENCY)
   - Evolution subscribes to:  recovery.recovery_resolved

3. Wire Detection subsystems:
   - Synthetic probes: 5 targets (one per service /health endpoint)
   - SLI/SLO: 2 SLIs per service (availability + latency_p99) with SLOs
   - Anomaly streams: 2 per service (response_latency + error_rate), Z=3.0 threshold
   - Threshold rules: 2 per service (error_rate: warn>5%/crit>15%, latency: warn>300ms/crit>1s)
   - Background data feed: polls all 5 services /health every 10s, feeds metrics into all 4 subsystems

4. Wire Absorption subsystems:
   - Circuit breakers: 12 total (one per service->dependency pair in dependency map)
   - Rate limiters: 5 (one per service, 100 req/s, burst 20)
   - Bulkheads: 5 (one per service, 50 max concurrent)
   - Blast radius graph: 7 nodes (5 services + postgres + redis), edges from dependency map
   - Degradation: 5 services x 4 tiers (Full/Reduced/Minimal/Emergency)

5. Wire Adaptation subsystems:
   - Feature flags: 30 total (6 per service: analytics, recommendations, search, experimental, core_api, auth)
   - Traffic routes: 5 services x 2 routes (primary at 100%, backup at 0%)
   - Auto-scaler: 5 services, current=1, min=1, max=10

6. Seed Evolution data:
   - 5 incident patterns for recurrence matching
   - Knowledge base entries from past incidents
   - Seeded post-incident reviews + tracked action items
```

### Service Dependency Map

```map
gateway --> orders, payments, inventory, notifications
orders  --> payments, inventory, notifications
payments --> postgres, redis
inventory --> postgres, redis
notifications --> redis
```

### Event Flow

The event bus is in-process pub/sub with topic routing:

```flow
Topic format: "category.event_type"
Wildcards: "category.*" or "*" (all events)

Flow:
  Detection fires "detection.alert_fired"
    -> Adaptation._on_alert() classifies anomaly, selects strategy, executes
    -> If adaptation window exceeded: publishes "adaptation.escalate_to_recovery"
      -> Recovery.begin_recovery() starts T0, escalates through T1-T4
      -> On resolution: publishes "recovery.recovery_resolved"
        -> Evolution auto-generates review, extracts actions, matches patterns

  Chaos "chaos.fault_injected" / "chaos.fault_rolled_back" tracked in timeline

  All events stored in bus._history (capped at 10,000) for timeline reconstruction
```

### Order Pipeline (Gateway)

```pipeline
POST /api/orders (gateway:8000)
  1. Create order    -> orders:8001/orders
  2. Process payment -> payments:8002/payments/process
  3. Reserve stock   -> inventory:8003/inventory/reserve
  4. Send receipt    -> notifications:8004/notifications/send
  Returns: {order, payment, stock, notification, pipeline: {total_ms, steps: [{step, status, latency_ms}]}}
```

---

## 5. Key Interfaces / Contracts

### Event Bus

```python
@dataclass
class Event:
    category: EventCategory       # detection | absorption | adaptation | recovery | evolution | system | chaos
    event_type: str               # "alert_fired", "circuit_breaker_opened", etc.
    severity: EventSeverity       # info | warning | critical | emergency
    payload: dict[str, Any]       # Arbitrary data
    source: str                   # "detection_engine", "chaos_injector", etc.
    event_id: str                 # UUID hex[:12]
    timestamp: float              # time.time()
    correlation_id: str | None    # Links related events across pillars
```

### Incident Model

```python
@dataclass
class Incident:
    incident_id: str              # "INC-{uuid[:8]}"
    severity: IncidentSeverity    # sev1 (critical) | sev2 (major) | sev3 (minor) | sev4 (low)
    status: IncidentStatus        # detected -> absorbing -> adapting -> recovering -> resolved -> post_review -> closed
    recovery_tier: RecoveryTier   # T0_EMERGENCY(0) | T1_MINIMUM(1) | T2_FUNCTIONAL(2) | T3_FULL(3) | T4_HARDENING(4)
    detection_class: DetectionClass  # threshold | anomaly | synthetic | change_correlation | human_observation | predictive
    anomaly_class: AnomalyClass   # transient | persistent | escalating
    timeline: list[dict]          # Chronological action entries
    correlation_id: str           # Links to event bus timeline
    # Timestamps for MTTD/MTTR: onset_time, detected_time, resolved_time
```

### ActionItem

```python
@dataclass
class ActionItem:
    action_id: str        # "ACT-{uuid[:8]}"
    incident_id: str
    title: str
    description: str
    owner: str
    priority: str         # high | medium | low
    status: str           # open | completed
    due_date: float | None
    pillar: str           # detection | absorption | adaptation | recovery | evolution
```

### CircuitBreaker

```python
class CircuitBreaker:
    # States: CLOSED -> OPEN -> HALF_OPEN -> CLOSED
    name: str                    # "gateway->orders"
    service: str                 # "gateway"
    dependency: str              # "orders"
    failure_threshold: int       # 5 (default from config)
    recovery_timeout: float      # 30s
    half_open_max_calls: int     # 3
    # async call(fn) -> raises CircuitBreakerError when OPEN
```

### FeatureFlag

```python
@dataclass
class FeatureFlag:
    name: str           # "gateway.analytics"
    service: str        # "gateway"
    enabled: bool       # True
    critical: bool      # Critical flags cannot be auto-disabled
    description: str
```

### TrafficRoute

```python
@dataclass
class TrafficRoute:
    target: str         # "orders-primary"
    weight: int         # 0-100 percentage
    healthy: bool
```

### Recovery Tiers

| Tier | Name | Window | Executor | Approval |
| ------ | ------ | -------- | ---------- | ---------- |
| T0 | Emergency Stabilization | 0-5 min | Automated | None required |
| T1 | Minimum Viable Recovery | 5-15 min | Incident Commander | None required |
| T2 | Functional Recovery | 15-60 min | Engineering Teams | IC approval |
| T3 | Full Restoration | 1-4 hours | Cross-functional | Management |
| T4 | Post-Incident Hardening | 1-2 weeks | Platform team | Planning |

Blueprint critical requirement: "T0 and T1 must execute without external dependencies or approvals."

Default runbooks loaded: T0 (5 automated steps), T1 (6 IC-led steps), T2 (5 engineering steps).
Additional runbooks loadable from YAML (see `runbooks/payment_failure.yml`).

### Maturity Model

5 levels per pillar (aligned with ISO 22316):

| Level | Name | Description |
| ------- | ------ | ------------- |
| L1 | Reactive | Ad-hoc, tribal knowledge |
| L2 | Managed | Basic monitoring, runbooks exist |
| L3 | Defined | Standardized processes, regular drills |
| L4 | Measured | Quantitative-driven, automated |
| L5 | Optimizing | Predictive, antifragile |

Assessment uses lambda-based criteria checks against a context dict per pillar.
CRS = SUM(w_i * M_i) for i=1..5, weighted by risk profile.

---

## 6. Infrastructure / Deployment

### Docker Compose Services

| Service | Image/Build | Port | Depends On |
| --------- | ------------- | ------ | ------------ |
| **postgres** | postgres:16-alpine | 5432 | - |
| **redis** | redis:7-alpine | 6379 | - |
| **prometheus** | prom/prometheus:latest | 9090 | - |
| **grafana** | grafana/grafana:latest | 3000 | - |
| **gateway** | Build from Dockerfile | 8000 | redis |
| **orders** | Build from Dockerfile | 8001 | postgres, redis |
| **payments** | Build from Dockerfile | 8002 | - |
| **inventory** | Build from Dockerfile | 8003 | - |
| **notifications** | Build from Dockerfile | 8004 | redis |
| **dashboard** | Build from Dockerfile | 8080 | gateway, orders, payments, inventory, notifications, prometheus |

### Dockerfile

```dockerfile
FROM python:3.11-slim
# Installs gcc, libpq-dev, curl
# COPY . . then pip install --no-cache-dir .
# Default CMD: uvicorn aref.dashboard.app:app --host 0.0.0.0 --port 8080
```

Each service overrides CMD in docker-compose.yml:

```cmd
uvicorn services.{name}.{name}_app:app --host 0.0.0.0 --port {port}
```

### Starting the Full Stack

```bash
docker compose up --build        # Build + start all services
docker compose up -d             # Detached mode
docker compose up dashboard      # Just the dashboard (starts dependencies)
```

### Direct Development (without Docker)

```bash
pip install -e ".[dev]"
# Start services individually:
uvicorn aref.dashboard.app:app --port 8080
uvicorn services.gateway.gateway_app:app --port 8000
uvicorn services.orders.orders_app:app --port 8001
uvicorn services.payments.payments_app:app --port 8002
uvicorn services.inventory.inventory_app:app --port 8003
uvicorn services.notifications.notifications_app:app --port 8004
```

### Environment Variables

| Variable | Purpose | Values |
| ---------- | --------- | -------- |
| `AREF_ENVIRONMENT` | Switches service URL resolution | `docker` = container hostnames, anything else = localhost |
| `AREF_DASHBOARD_PORT` | Dashboard port override | Default: 8080 |
| `AREF_DEBUG` | Debug mode | Default: true |
| `AREF_LOG_LEVEL` | Log verbosity | Default: INFO |
| `AREF_RISK_PROFILE` | CRS weight profile | `balanced` (default), `availability_critical`, `data_integrity_critical`, `innovation_heavy` |
| `AREF_DB_*` | PostgreSQL connection | HOST, PORT, NAME, USER, PASSWORD |
| `AREF_REDIS_*` | Redis connection | HOST, PORT, DB, PASSWORD |
| `AREF_DETECTION_*` | Detection thresholds | See DetectionConfig fields |
| `AREF_ABSORPTION_*` | Absorption thresholds | See AbsorptionConfig fields |
| `AREF_ADAPTATION_*` | Adaptation thresholds | See AdaptationConfig fields |
| `AREF_RECOVERY_*` | Recovery time targets | See RecoveryConfig fields |
| `AREF_EVOLUTION_*` | Evolution velocity targets | See EvolutionConfig fields |
| `GF_SECURITY_ADMIN_PASSWORD` | Grafana admin password | Default: `aref` |

---

## 7. Current State: Done vs. Planned

### Fully Implemented

| Component | Status | Notes |
| ----------- | -------- | ------- |
| **Core framework** (config, events, metrics, models, logging) | Complete | Singleton patterns, async event bus, all AREF formulas |
| **Detection pillar** | Complete | All 4 detection classes operational, live data feed every 10s, alert lifecycle |
| **Absorption pillar** | Complete | Circuit breakers, bulkheads, rate limiters, blast radius, degradation — all wired |
| **Adaptation pillar** | Complete | Decision tree, feature flags, traffic shifting, scaling — event-driven |
| **Recovery pillar** | Complete | T0-T4 tiered engine, runbook executor, YAML loading |
| **Evolution pillar** | Complete | Auto-review generation, action tracking, pattern matching, knowledge base |
| **Maturity model** | Complete | L1-L5 assessment, CRS scoring across 4 risk profiles |
| **Chaos engineering** | Complete | 5 experiments, fault injector with safety bounds + auto-rollback |
| **5 microservices** | Complete | Gateway, Orders, Payments, Inventory, Notifications — all enhanced |
| **Service factory** | Complete | Shared health/readyz/info/metrics endpoints |
| **Dashboard API** | Complete | 19 REST endpoints covering all pillars |
| **Dashboard UI** | Complete | 6 tabs: Overview, Detection, Absorption, Adaptation, Services, Timeline |
| **CLI** | Complete | 7 commands: status, pillars, maturity, chaos, chaos-stop, timeline, serve |
| **Demo script** | Complete | 12-step Rich terminal demo with CLI args, pillar deep-dive, comparison |
| **Prometheus integration** | Complete | /metrics endpoints on all services, scrape config |
| **Grafana provisioning** | Partial | Datasource provisioned, no dashboard JSON defined |
| **Tests** | Partial | 14 unit test classes + 2 integration tests covering core + all pillars |

### Known Gaps / Not Yet Implemented

- **Database persistence**: PostgreSQL is provisioned in Docker but not used — all state is in-memory
- **Redis usage**: Redis is provisioned but not used for caching/queuing — services use in-memory structures
- **Grafana dashboards**: Datasource is provisioned but no pre-built dashboard JSON panels
- **Authentication/authorization**: CORS is wide-open (`allow_origins=["*"]`), no auth on endpoints
- **Real scaling**: AutoScaler is simulated (in-memory counter), not wired to Docker/K8s
- **Predictive detection**: Level 5 maturity criteria reference predictive detection, not implemented
- **Dashboard Evolution tab**: Placeholder or partially built (noted as in-progress in prior sessions)
- **Dashboard Services tab**: Had visual issues (status dots, empty panels) noted but not fully debugged
- **Schema fallback**: Listed in adaptation strategies but not implemented
- **Alembic migrations**: Listed as dependency but no migrations directory exists
- **Textual TUI**: Listed as dependency but not used (CLI uses Click + Rich instead)
- **No .env file**: All config relies on env vars or hardcoded defaults, no .env.example template
- **No git repository**: Project has not been initialized with git

### What demo.py Exercises

The demo exercises the **full D-A-A-R-E lifecycle** through the running stack:

1. Preflight health check (all 6 services)
2. Baseline CRS snapshot
3. Baseline traffic (order pipeline through gateway)
4. Service deep health (gateway's deep-health endpoint)
5. Chaos injection (any of 5 experiments via API)
6. Incident traffic (observe failover, provider switching)
7. During-incident CRS + pillar deep-dive (Detection, Absorption, Adaptation, Recovery, Evolution)
8. Event timeline
9. Chaos rollback
10. Recovery traffic
11. Final CRS snapshot
12. Before/after comparison + traffic summary

What it does NOT exercise: maturity assessment, runbook execution, evolution auto-review generation (these happen in-process via event bus, not exposed through the demo's HTTP-only approach).

---

## 8. Dependencies

### Python Dependencies (from pyproject.toml)

**Runtime:**

| Package | Version | Purpose |
| --------- | --------- | --------- |
| fastapi | >=0.110.0 | Web framework for services + dashboard |
| uvicorn[standard] | >=0.27.0 | ASGI server |
| httpx | >=0.27.0 | Async HTTP client (inter-service calls, synthetic probes) |
| sqlalchemy[asyncio] | >=2.0.25 | ORM (provisioned, not actively used) |
| asyncpg | >=0.29.0 | PostgreSQL async driver (provisioned, not actively used) |
| alembic | >=1.13.0 | DB migrations (provisioned, no migrations defined) |
| redis[hiredis] | >=5.0.0 | Redis client (provisioned, not actively used) |
| prometheus-client | >=0.20.0 | Metrics exposition |
| prometheus-fastapi-instrumentator | >=7.0.0 | Auto-instrument FastAPI |
| pydantic | >=2.6.0 | Data validation |
| pydantic-settings | >=2.1.0 | Env-driven config |
| rich | >=13.7.0 | Terminal UI (CLI + demo) |
| textual | >=0.50.0 | TUI framework (listed, not used) |
| click | >=8.1.0 | CLI command framework |
| numpy | >=1.26.0 | Anomaly detection math |
| scikit-learn | >=1.4.0 | Isolation Forest model |
| apscheduler | >=3.10.0 | Task scheduling (listed, not actively used) |
| tenacity | >=8.2.0 | Retry library (listed, not actively used) |
| pyyaml | >=6.0.0 | Runbook YAML parsing |
| structlog | >=24.1.0 | Structured logging |
| jinja2 | >=3.1.0 | Template rendering |
| plotly | >=5.18.0 | Charts (listed, dashboard uses JS canvas instead) |

**Dev:**

| Package | Version | Purpose |
| --------- | --------- | --------- |
| pytest | >=8.0.0 | Testing |
| pytest-asyncio | >=0.23.0 | Async test support |
| pytest-cov | >=4.1.0 | Coverage |
| ruff | >=0.2.0 | Linting |
| mypy | >=1.8.0 | Type checking |

**No Node/npm dependencies.** The dashboard is pure HTML/CSS/JS served by FastAPI's StaticFiles.

### CLI Entrypoints

```toml
[project.scripts]
aref = "aref.cli.main:cli"           # aref status | aref pillars | aref chaos ...
aref-demo = "scripts.demo:main"       # aref-demo --experiment ... --orders ... --fast
```

### Build System

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["aref", "services", "chaos", "scripts"]
```

---

## 9. File Naming Conventions

### Service Files: `{service}_app.py`

All 5 microservice files follow the `{service}_app.py` convention:

- `services/gateway/gateway_app.py`
- `services/orders/orders_app.py`
- `services/payments/payments_app.py`
- `services/inventory/inventory_app.py`
- `services/notifications/notifications_app.py`

This is reflected in both `docker-compose.yml` uvicorn commands and local development:

```yaml
command: uvicorn services.gateway.gateway_app:app --host 0.0.0.0 --port 8000
```

### Metadata Headers

All major files use the established metadata format:

```meta
"""
Metadata
    - Title: ...
    - File Name: ...
    - Relative Path: ...
    - Artifact Type: script
    - Version: 2.0.0
    - Date: 2026-03-13
    - Author: Dennis 'dnoice' Smaltz
    - A.I. Acknowledgement: Anthropic - Claude Opus 4
    - Signature: ︻デ═─── ... | Aim Twice, Shoot Once!

Description:
    ...

Key Features:
    ...

Usage Instructions:
    ...
---------
"""
```

### Other Patterns

- Package `__init__.py` files contain single-line docstrings describing the module
- Engine classes follow the pattern: `__init__`, `start()`, `stop()`, `get_status() -> dict`
- Singleton access via `get_X()` / `reset_X()` module-level functions (config, event bus, metrics engine, circuit breaker registry)
- Test files: `test_{module}.py` with `Test{Class}` classes

---

## 10. Version / Branch State

- **Version**: 2.0.0 (defined in `aref/__init__.py` and `pyproject.toml`)
- **Git**: Not initialized — no `.git` directory, no branches, no commit history
- **Recent major work**: Service enhancement (all 5 services expanded 2-4x), service factory (`base.py`) rewrite, dashboard Timeline tab build, demo script rewrite with Rich UI

---

## Appendix: API Endpoint Reference

### Dashboard Control Plane (port 8080)

| Method | Endpoint | Returns |
| -------- | ---------- | --------- |
| GET | `/` | Dashboard HTML SPA |
| GET | `/api/aref/status` | CRS, pillar scores, risk profile, chaos status |
| GET | `/api/aref/services` | All service health + versions |
| GET | `/api/aref/alerts` | Active alerts from detection engine |
| GET | `/api/aref/timeline` | Events (up to 100) + summary (by_category, by_severity, by_source) |
| GET | `/api/aref/detection` | Threshold status, anomaly stats, SLI tracker, active alerts |
| GET | `/api/aref/absorption` | Circuit breakers, rate limiters, bulkheads, blast radius, degradation |
| GET | `/api/aref/adaptation` | Feature flags, traffic shifter, scaler, active/total adaptations |
| GET | `/api/aref/recovery` | Active recoveries, total recovered, runbooks |
| GET | `/api/aref/evolution` | Reviews, action tracker stats, knowledge base, improvement velocity, patterns |
| GET | `/api/aref/maturity` | Full maturity assessment across all profiles |
| GET | `/api/aref/metrics` | MTTD, MTTR, availability, error budgets, CRS per profile |
| POST | `/api/aref/chaos/start` | Start chaos experiment `{"experiment": "..."}` |
| POST | `/api/aref/chaos/stop` | Stop all chaos + rollback |
| GET | `/api/aref/chaos/status` | Active injections |
| GET | `/metrics` | Prometheus metrics (text format) |

### Per-Service Endpoints (shared via base.py)

| Endpoint | Purpose |
| ---------- | --------- |
| `/health` | Uptime, total_requests, total_errors, error_rate, memory_mb |
| `/healthz` | K8s liveness probe (200 OK) |
| `/readyz` | K8s readiness probe (200 or 503) |
| `/info` | Service name, version, dependencies, python version, platform, PID |
| `/metrics` | Prometheus metrics |
| `/chaos/enable` | Enable chaos injection (type, rate, delay) |
| `/chaos/disable` | Disable chaos injection |

### Service-Specific Highlights

**Gateway (8000):** `/api/orders` (full pipeline), `/api/services/deep-health`, `/api/gateway/stats`, `/api/gateway/requests`

**Orders (8001):** `/orders` (CRUD + filters), `/orders/{id}/confirm`, `/orders/{id}/cancel`, `/orders/audit/log`, `/orders/stats/summary`

**Payments (8002):** `/payments/process`, `/payments/{id}/refund`, `/payments/settle`, `/payments/providers/health`, `/payments/providers/reset`, `/payments/stats/summary`

**Inventory (8003):** `/inventory/stock`, `/inventory/reserve`, `/inventory/release/{id}`, `/inventory/replenish`, `/inventory/adjust`, `/inventory/movements`, `/inventory/catalog`, `/inventory/stats`

**Notifications (8004):** `/notifications/send`, `/notifications/batch`, `/notifications/shed-level`, `/notifications/templates`, `/notifications/history`, `/notifications/stats`

---

## Appendix: Chaos Experiments

| Name | Target | Fault | Rate | Duration | Hypothesis |
| ------ | -------- | ------- | ------ | ---------- | ------------ |
| `payment_provider_failure` | payments | error | 80% | 120s | CB opens in 30s, system switches to backup provider |
| `order_service_latency` | orders | latency (3s) | 70% | 90s | Anomaly detection fires in 3min, auto-scaler adds instances |
| `inventory_degradation` | inventory | error | 60% | 60s | Inventory degrades to cached/minimal mode, orders still process |
| `notification_overload` | notifications | latency (5s) | 90% | 60s | Feature flags disable notifications, core flow unaffected |
| `cascading_failure` | payments | error | 95% | 180s | Full D-A-A-R-E pipeline activates, recovery in 15min, auto-review |

Safety bounds enforced: max 90% fault rate, max 5 minute duration, auto-rollback on expiry.

---

## Session Objective

**Goal:** Develop a comprehensive refactoring and restructuring plan for the AREF v2.0.0 codebase, focused on four pillars of code quality: separation of concerns, modularity, maintainability, and extensibility for ongoing improvements and fixes.

**What we need to produce:**

1. **Architectural Review** — Evaluate the current codebase against software engineering best practices, identifying where responsibilities are tangled, where modules are doing too much, where coupling is too tight, and where the boundaries between framework, services, and infrastructure are blurred.

2. **Dependency Audit** — Flag the provisioned-but-unused dependencies (SQLAlchemy, asyncpg, alembic, redis, textual, apscheduler, tenacity, plotly) and recommend keep/remove/defer decisions for each. Clean up the dependency footprint so what's declared matches what's actually used.

3. **Separation of Concerns Assessment** — Specifically examine:
   - The 1176-line `dashboard/app.py` that handles lifespan wiring, engine initialization, seed data, AND 19 API endpoints in a single file
   - Service files that mix business logic, chaos injection, and metrics registration in flat scripts
   - The boundary between the AREF framework package (`aref/`) and the demo microservices (`services/`) — are they properly decoupled?
   - Whether `aref/core/` is the right home for everything currently in it, or if some pieces should be elevated or redistributed
   - The monolithic `dashboard.css` (2149 lines) and `dashboard.js` (2758 lines) — the stylesheet bundles design tokens, reset, layout, sidebar, cards, every pillar-specific panel style, metrics page components, animations, and timeline into a single file with no modular structure. The JavaScript bundles configuration, state management, API client, polling loop, DOM rendering for all six tabs, SVG chart generation, gauge animation, chaos controls, and navigation into a single IIFE. Both need to be decomposed into properly separated modules (CSS partials or scoped files per component/view, JS modules per concern — API layer, state, rendering per tab, shared utilities, chart components).

4. **Modularity Plan** — Propose concrete file splits, module reorganizations, and interface boundaries that would allow:
   - Individual pillars to be developed, tested, and deployed independently
   - The dashboard to be a thin API layer over the engines, not the wiring hub
   - Seed data and demo concerns to be fully separated from production code paths
   - New pillar features (predictive detection, schema fallback, etc.) to be added without touching existing files

5. **Maintainability Roadmap** — Address the known gaps that impact long-term health:
   - Git initialization and branching strategy
   - `.env.example` template for onboarding new developers
   - Test coverage expansion strategy (what's tested, what's not, priority order)
   - Documentation gaps (README is a stub, no CONTRIBUTING guide, no architecture diagram)
   - Linting/formatting enforcement (ruff and mypy are declared as dev deps but no config or CI)

6. **Prioritized Action Plan** — Deliver the refactoring work as a phased, ordered list — not a wish list, but a sequenced plan where each phase builds on the previous one, with clear "done" criteria per phase. Phase 1 should be achievable in a single working session; later phases can span multiple sessions.

**Constraints:**

- No functional regressions — the demo, dashboard, CLI, and all services must continue to work after each phase
- Preserve the existing docstring standard on all new/modified files
- Maintain the `*_app.py` naming convention for services
- Keep the in-memory architecture for now — database persistence is a future phase, not part of this refactor
- All recommendations should be concrete (specific files, specific splits, specific moves) — not abstract principles

---

︻デ═─── ✦ ✦ ✦
