"""
✒ Metadata
    - Title: AREF Control Plane API (AREF Edition - v2.0)
    - File Name: app.py
    - Relative Path: aref/dashboard/app.py
    - Artifact Type: script
    - Version: 2.0.0
    - Date: 2026-03-13
    - Update: Thursday, March 13, 2026
    - Author: Dennis 'dnoice' Smaltz
    - A.I. Acknowledgement: Anthropic - Claude Opus 4
    - Signature: ︻デ═─── ✦ ✦ ✦ | Aim Twice, Shoot Once!

✒ Description:
    Central FastAPI application serving the AREF web dashboard and REST API.
    Delegates engine initialization to the engines module, subsystem wiring
    to bootstrap, seed data to seed_data, background polling to background,
    and API routes to the routes package.

✒ Key Features:
    - Feature 1: Async lifespan manager orchestrating startup and shutdown
    - Feature 2: Router-based API organization (status, pillars, metrics, chaos)
    - Feature 3: Prometheus /metrics endpoint for external monitoring
    - Feature 4: CORS-enabled with static file serving for the dashboard SPA
    - Feature 5: Docker-aware via AREF_ENVIRONMENT variable

✒ Usage Instructions:
    Start the server with uvicorn:
        $ uvicorn aref.dashboard.app:app --host 0.0.0.0 --port 8080

    Or via Docker Compose (preferred for full microservice stack):
        $ docker compose up dashboard

    API documentation auto-generated at:
        http://localhost:8080/docs  (Swagger UI)
        http://localhost:8080/redoc (ReDoc)

✒ Examples:
    $ curl http://localhost:8080/api/aref/status
    $ curl http://localhost:8080/api/aref/detection
    $ curl -X POST http://localhost:8080/api/aref/chaos/start -d '{"experiment":"payment_provider_failure"}'

✒ Other Important Information:
    - Dependencies:
        Required: fastapi, uvicorn, structlog, prometheus_client
        Internal: aref.dashboard.engines, aref.dashboard.bootstrap,
                  aref.dashboard.seed_data, aref.dashboard.background,
                  aref.dashboard.routes
    - Compatible platforms: Linux, macOS, Docker (Python 3.11+)
    - Security considerations: CORS is wide-open — restrict in production
---------
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from aref.core.config import get_config
from aref.core.events import get_event_bus
from aref.core.logging import setup_logging
from aref.dashboard.engines import get_engines

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

from aref.dashboard.routes.status import router as status_router
from aref.dashboard.routes.pillars import router as pillars_router
from aref.dashboard.routes.metrics import router as metrics_router
from aref.dashboard.routes.chaos import router as chaos_router

logger = structlog.get_logger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
TEMPLATE_DIR = Path(__file__).parent / "templates"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    e = get_engines()
    config = get_config()
    setup_logging(level=config.log_level)
    bus = get_event_bus()

    # Initialize engines
    e.detection_engine = DetectionEngine(bus)
    e.adaptation_engine = AdaptationEngine(bus)
    e.recovery_engine = RecoveryEngine(bus)
    e.evolution_engine = EvolutionEngine(bus)
    e.fault_injector = FaultInjector()
    e.experiment_runner = ExperimentRunner(e.fault_injector)
    e.maturity_assessor = MaturityAssessor()
    e.rate_limiter_mgr = RateLimiterManager()
    e.bulkhead_mgr = BulkheadManager()
    e.blast_radius = BlastRadiusAnalyzer()
    e.degradation_mgr = DegradationManager()

    # Start engines
    await e.detection_engine.start()
    await e.adaptation_engine.start()
    await e.recovery_engine.start()
    await e.evolution_engine.start()

    # Wire subsystems (detection, absorption, adaptation)
    from aref.dashboard.bootstrap import wire_subsystems
    _services, _live_metrics, feed_task = await wire_subsystems(e, config)

    # Load evolution seed data
    from aref.dashboard.seed_data import load_seed_data
    await load_seed_data(e.evolution_engine)

    logger.info("aref.platform.started", version="2.0.0")

    yield

    # Shutdown
    feed_task.cancel()
    await e.detection_engine.stop()
    await e.adaptation_engine.stop()
    await e.recovery_engine.stop()
    await e.evolution_engine.stop()
    logger.info("aref.platform.stopped")


# Create the FastAPI app
app = FastAPI(
    title="AREF Control Plane",
    description="Adaptive Resilience Engineering Framework — Dashboard & API",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Include route modules
app.include_router(status_router)
app.include_router(pillars_router)
app.include_router(metrics_router)
app.include_router(chaos_router)


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return (TEMPLATE_DIR / "index.html").read_text()


@app.get("/metrics")
async def prometheus_metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
