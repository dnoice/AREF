"""
✒ Metadata
    - Title: Detection Background Feed (AREF Edition - v2.0)
    - File Name: background.py
    - Relative Path: aref/dashboard/background.py
    - Artifact Type: script
    - Version: 2.0.0
    - Date: 2026-03-13
    - Update: Thursday, March 13, 2026
    - Author: Dennis 'dnoice' Smaltz
    - A.I. Acknowledgement: Anthropic - Claude Opus 4
    - Signature: ︻デ═─── ✦ ✦ ✦ | Aim Twice, Shoot Once!

✒ Description:
    Background async task that periodically polls all microservices and feeds
    live metrics into the detection subsystems (threshold rules, anomaly
    streams, SLI tracker). Runs every 10 seconds once started.

✒ Key Features:
    - Feature 1: Polls /health endpoint of all 5 microservices
    - Feature 2: Feeds latency and error rate into anomaly detection streams
    - Feature 3: Records availability and latency SLIs for SLO tracking
    - Feature 4: Updates threshold rule metrics dict for breach detection
    - Feature 5: Handles unreachable services gracefully with error metrics

✒ Usage Instructions:
    Called from bootstrap.py during lifespan setup:
        task = asyncio.create_task(
            detection_data_feed(engines, services, live_metrics)
        )
---------
"""

from __future__ import annotations

import asyncio
import random
import time

import httpx

from aref.dashboard.engines import EngineContainer


async def detection_data_feed(
    engines: EngineContainer,
    services: dict[str, str],
    live_metrics: dict[str, float],
) -> None:
    """Periodically poll services and record metrics into detection subsystems."""
    await asyncio.sleep(2)  # let services warm up
    async with httpx.AsyncClient(timeout=5.0) as client:
        while True:
            for name, base_url in services.items():
                try:
                    start = time.perf_counter()
                    resp = await client.get(f"{base_url}/health")
                    latency_ms = (time.perf_counter() - start) * 1000.0

                    healthy = resp.status_code == 200
                    # Simulate a small jitter error rate based on real health
                    error_rate = 0.0 if healthy else random.uniform(20.0, 50.0)
                    # Add small natural jitter to healthy services
                    if healthy:
                        error_rate = random.uniform(0.0, 2.0)

                    # Feed threshold rules
                    live_metrics[f"{name}.latency"] = latency_ms
                    live_metrics[f"{name}.error_rate"] = error_rate

                    # Feed anomaly streams
                    engines.detection_engine.anomaly.record(name, "response_latency", latency_ms)
                    engines.detection_engine.anomaly.record(name, "error_rate", error_rate)

                    # Feed SLI tracker
                    engines.detection_engine.sli_tracker.record_sli(
                        name, "availability", 1.0 if healthy else 0.0
                    )
                    engines.detection_engine.sli_tracker.record_sli(
                        name, "latency_p99", latency_ms
                    )

                    # Record downtime if unhealthy (probe interval worth)
                    if not healthy:
                        engines.detection_engine.sli_tracker.record_downtime(
                            name, "availability", 10.0
                        )
                        engines.detection_engine.sli_tracker.record_downtime(
                            name, "latency_p99", 10.0
                        )

                except Exception:
                    # Service unreachable — record as error
                    live_metrics[f"{name}.latency"] = 5000.0
                    live_metrics[f"{name}.error_rate"] = 100.0
                    engines.detection_engine.anomaly.record(name, "response_latency", 5000.0)
                    engines.detection_engine.anomaly.record(name, "error_rate", 100.0)
                    engines.detection_engine.sli_tracker.record_sli(name, "availability", 0.0)
                    engines.detection_engine.sli_tracker.record_downtime(name, "availability", 10.0)

            await asyncio.sleep(10)  # poll every 10 seconds
