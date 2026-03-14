"""
✒ Metadata
    - Title: Chaos Engineering Routes (AREF Edition - v2.0)
    - File Name: chaos.py
    - Relative Path: aref/dashboard/routes/chaos.py
    - Artifact Type: script
    - Version: 2.0.0
    - Date: 2026-03-13
    - Update: Thursday, March 13, 2026
    - Author: Dennis 'dnoice' Smaltz
    - A.I. Acknowledgement: Anthropic - Claude Opus 4
    - Signature: ︻デ═─── ✦ ✦ ✦ | Aim Twice, Shoot Once!

✒ Description:
    FastAPI router for chaos engineering experiment control. Provides
    endpoints to start fault injection experiments, stop all active
    injections with rollback, and query current chaos status.

✒ Key Features:
    - Feature 1: Start named chaos experiments with fault injection
    - Feature 2: Stop all active injections with automatic rollback
    - Feature 3: Query active injection status

✒ Usage Instructions:
    Included in app.py via app.include_router(chaos_router)
---------
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from aref.dashboard.engines import get_engines
from chaos.experiments import EXPERIMENTS

router = APIRouter()


@router.post("/api/aref/chaos/start")
async def start_chaos(request: Request) -> dict[str, Any]:
    eng = get_engines()
    if not eng.fault_injector:
        return {"error": "Chaos module not initialized"}
    body = await request.json()
    experiment_name = body.get("experiment", "")

    exp = next((x for x in EXPERIMENTS if x.name == experiment_name), None)
    if not exp:
        return {"error": f"Unknown experiment: {experiment_name}"}

    injection = await eng.fault_injector.inject(
        target_service=exp.target_service,
        fault_type=exp.fault_type,
        rate=exp.fault_rate,
        duration=exp.duration,
        parameters=exp.parameters,
    )
    return {"status": "started", "injection": injection.injection_id, "experiment": experiment_name}


@router.post("/api/aref/chaos/stop")
async def stop_chaos() -> dict[str, Any]:
    eng = get_engines()
    if not eng.fault_injector:
        return {"error": "Chaos module not initialized"}
    count = await eng.fault_injector.rollback_all()
    return {"status": "stopped", "rolled_back": count}


@router.get("/api/aref/chaos/status")
async def chaos_status() -> dict[str, Any]:
    eng = get_engines()
    if not eng.fault_injector:
        return {"active": []}
    return eng.fault_injector.get_status()
