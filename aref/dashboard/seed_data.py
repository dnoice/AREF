"""
✒ Metadata
    - Title: Evolution Seed Data Loader (AREF Edition - v2.0)
    - File Name: seed_data.py
    - Relative Path: aref/dashboard/seed_data.py
    - Artifact Type: script
    - Version: 2.0.0
    - Date: 2026-03-13
    - Update: Thursday, March 13, 2026
    - Author: Dennis 'dnoice' Smaltz
    - A.I. Acknowledgement: Anthropic - Claude Opus 4
    - Signature: ︻デ═─── ✦ ✦ ✦ | Aim Twice, Shoot Once!

✒ Description:
    Loads seed data into the Evolution engine for demonstration and baseline
    testing. Populates incident patterns, knowledge base entries, post-incident
    reviews, and action items across all five pillars.

✒ Key Features:
    - Feature 1: Five incident patterns for recurrence matching across services
    - Feature 2: Three knowledge base entries with blast radius and timing data
    - Feature 3: Three seeded post-incident reviews with lessons learned
    - Feature 4: Eight action items across detection, absorption, adaptation,
                  recovery, and evolution pillars
    - Feature 5: Mix of completed, open, and overdue items for realistic state

✒ Usage Instructions:
    Called during dashboard lifespan startup:
        await load_seed_data(evolution_engine)
---------
"""

from __future__ import annotations

import time

from aref.core.models import ActionItem
from aref.evolution.engine import EvolutionEngine


async def load_seed_data(evolution_engine: EvolutionEngine) -> None:
    """Populate the Evolution engine with seed data for demos and baseline state."""

    # Known incident patterns for recurrence matching
    sample_patterns = [
        {
            "service": "gateway",
            "detection_class": "threshold",
            "severity": "sev2",
            "contributing_factors": ["high_latency", "connection_pool_exhaustion"],
            "affected_services": ["gateway", "orders", "payments"],
            "created_from": "INC-SEED-001",
            "_match_count": 1,
        },
        {
            "service": "payments",
            "detection_class": "anomaly",
            "severity": "sev1",
            "contributing_factors": ["database_timeout", "connection_leak"],
            "affected_services": ["payments", "orders"],
            "created_from": "INC-SEED-002",
            "_match_count": 0,
        },
        {
            "service": "inventory",
            "detection_class": "threshold",
            "severity": "sev3",
            "contributing_factors": ["cache_miss_spike", "cold_start"],
            "affected_services": ["inventory"],
            "created_from": "INC-SEED-003",
            "_match_count": 2,
        },
        {
            "service": "orders",
            "detection_class": "change_correlation",
            "severity": "sev2",
            "contributing_factors": ["deploy_regression", "schema_mismatch"],
            "affected_services": ["orders", "inventory"],
            "created_from": "INC-SEED-004",
            "_match_count": 0,
        },
        {
            "service": "notifications",
            "detection_class": "synthetic",
            "severity": "sev3",
            "contributing_factors": ["redis_latency", "queue_backlog"],
            "affected_services": ["notifications"],
            "created_from": "INC-SEED-005",
            "_match_count": 1,
        },
    ]
    for pat in sample_patterns:
        evolution_engine.pattern_matcher.register_pattern(pat)

    # Seed knowledge base with past incident learnings
    sample_kb_entries = [
        {
            "incident_id": "INC-SEED-001",
            "source_service": "gateway",
            "severity": "sev2",
            "detection_class": "threshold",
            "time_to_detect": 120,
            "time_to_recover": 480,
            "blast_radius": {"containment_pct": 78},
        },
        {
            "incident_id": "INC-SEED-002",
            "source_service": "payments",
            "severity": "sev1",
            "detection_class": "anomaly",
            "time_to_detect": 45,
            "time_to_recover": 1200,
            "blast_radius": {"containment_pct": 92},
        },
        {
            "incident_id": "INC-SEED-003",
            "source_service": "inventory",
            "severity": "sev3",
            "detection_class": "threshold",
            "time_to_detect": 300,
            "time_to_recover": 180,
            "blast_radius": {"containment_pct": 100},
        },
    ]
    sample_reviews = [
        {
            "generated_at": time.time() - 86400 * 7,
            "incident_id": "INC-SEED-001",
            "severity": "sev2",
            "summary": "SEV2 incident affecting gateway. Duration: 480s. Detection class: threshold.",
            "contributing_factors": [
                {"factor": "Insufficient blast radius containment", "category": "absorption",
                 "description": "3 services affected. Review isolation boundaries."},
            ],
            "response_effectiveness": {"detection": "effective", "absorption": "needs_improvement",
                                       "adaptation": "effective", "recovery": "effective"},
            "detection_effectiveness": 0.8,
            "blast_radius_containment": 78,
            "adaptation_latency": 12,
            "recovery_duration": 480,
            "mttd": 120,
            "lessons_learned": ["Blast radius containment needs tighter circuit breaker thresholds on gateway deps."],
            "blameless_note": "This review follows AREF blameless principles.",
        },
        {
            "generated_at": time.time() - 86400 * 3,
            "incident_id": "INC-SEED-002",
            "severity": "sev1",
            "summary": "SEV1 incident affecting payments. Duration: 1200s. Detection class: anomaly.",
            "contributing_factors": [
                {"factor": "Delayed detection", "category": "detection",
                 "description": "MTTD exceeded 5-minute target, delaying downstream response."},
            ],
            "response_effectiveness": {"detection": "effective", "absorption": "effective",
                                       "adaptation": "needs_improvement", "recovery": "needs_improvement"},
            "detection_effectiveness": 0.925,
            "blast_radius_containment": 92,
            "adaptation_latency": 35,
            "recovery_duration": 1200,
            "mttd": 45,
            "lessons_learned": ["Recovery exceeded 15-minute target. Review T0/T1 runbook automation.",
                                "Automated adaptation was not triggered. Add or verify adaptation rules."],
            "blameless_note": "This review follows AREF blameless principles.",
        },
        {
            "generated_at": time.time() - 86400 * 1,
            "incident_id": "INC-SEED-003",
            "severity": "sev3",
            "summary": "SEV3 incident affecting inventory. Duration: 180s. Detection class: threshold.",
            "contributing_factors": [],
            "response_effectiveness": {"detection": "needs_improvement", "absorption": "effective",
                                       "adaptation": "effective", "recovery": "effective"},
            "detection_effectiveness": 0.5,
            "blast_radius_containment": 100,
            "adaptation_latency": 8,
            "recovery_duration": 180,
            "mttd": 300,
            "lessons_learned": ["Detection thresholds should be reviewed and tightened for this service."],
            "blameless_note": "This review follows AREF blameless principles.",
        },
    ]
    for inc, rev in zip(sample_kb_entries, sample_reviews):
        evolution_engine.knowledge_base.store_incident(inc, rev)
        evolution_engine._reviews.append(rev)

    # Seed action items across pillars
    now = time.time()
    seed_actions = [
        ActionItem(incident_id="INC-SEED-001", title="Tighten gateway circuit breaker thresholds",
                   description="Reduce failure_threshold from 5 to 3 on gateway->orders and gateway->payments.",
                   priority="high", pillar="absorption", status="completed",
                   created_at=now - 86400 * 6, completed_at=now - 86400 * 4),
        ActionItem(incident_id="INC-SEED-001", title="Add bulkhead to gateway->notifications",
                   description="Prevent notification failures from consuming gateway thread pool.",
                   priority="medium", pillar="absorption", status="completed",
                   created_at=now - 86400 * 6, completed_at=now - 86400 * 2),
        ActionItem(incident_id="INC-SEED-001", title="Document incident learnings",
                   description="Share incident review with the broader organization within 72 hours.",
                   priority="medium", pillar="evolution", status="completed",
                   created_at=now - 86400 * 7, completed_at=now - 86400 * 5),
        ActionItem(incident_id="INC-SEED-002", title="Reduce adaptation latency for payments",
                   description="Automate adaptation triggers that are currently manual.",
                   priority="medium", pillar="adaptation", status="open",
                   created_at=now - 86400 * 3),
        ActionItem(incident_id="INC-SEED-002", title="Improve recovery time for payments",
                   description="Review and automate T0/T1 runbooks for faster stabilization.",
                   priority="high", pillar="recovery", status="open",
                   created_at=now - 86400 * 3, due_date=now - 86400 * 1),  # overdue
        ActionItem(incident_id="INC-SEED-002", title="Document incident learnings",
                   description="Share incident review with the broader organization within 72 hours.",
                   priority="medium", pillar="evolution", status="open",
                   created_at=now - 86400 * 3, due_date=now + 86400 * 1),
        ActionItem(incident_id="INC-SEED-003", title="Improve detection coverage for inventory",
                   description="MTTD was 300s. Review alert thresholds and add anomaly detection.",
                   priority="high", pillar="detection", status="open",
                   created_at=now - 86400 * 1),
        ActionItem(incident_id="INC-SEED-003", title="Document incident learnings",
                   description="Share incident review with the broader organization within 72 hours.",
                   priority="medium", pillar="evolution", status="open",
                   created_at=now - 86400 * 1, due_date=now + 86400 * 2),
    ]
    for action in seed_actions:
        evolution_engine.action_tracker.add(action)
