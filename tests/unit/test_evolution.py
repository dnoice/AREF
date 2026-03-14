"""
Tests for AREF Evolution pillar — pattern matching, action tracking,
knowledge base, and post-incident review generation.
"""

import time

import pytest

from aref.core.events import Event, EventCategory, EventSeverity, get_event_bus, reset_event_bus
from aref.core.models import ActionItem
from aref.evolution.patterns import PatternMatcher
from aref.evolution.tracker import ActionTracker
from aref.evolution.knowledge_base import KnowledgeBase
from aref.evolution.post_incident import PostIncidentReviewGenerator


class TestPatternMatcher:
    def setup_method(self):
        self.matcher = PatternMatcher()

    def test_register_and_find_match(self):
        self.matcher.register_pattern({
            "service": "payments",
            "detection_class": "threshold",
            "severity": "sev1",
            "contributing_factors": ["timeout"],
        })
        matches = self.matcher.find_matches({
            "source_service": "payments",
            "detection_class": "threshold",
            "severity": "sev1",
        })
        assert len(matches) == 1
        assert matches[0]["match_score"] >= 3

    def test_no_match_below_threshold(self):
        self.matcher.register_pattern({
            "service": "orders",
            "detection_class": "anomaly",
            "severity": "sev1",
        })
        matches = self.matcher.find_matches({
            "source_service": "payments",
            "detection_class": "threshold",
            "severity": "sev3",
        })
        assert len(matches) == 0

    def test_contributing_factors_boost_score(self):
        self.matcher.register_pattern({
            "service": "gateway",
            "detection_class": "threshold",
            "severity": "sev1",
            "contributing_factors": ["memory_leak", "gc_pressure"],
        })
        matches = self.matcher.find_matches({
            "source_service": "gateway",
            "detection_class": "anomaly",
            "severity": "sev2",
            "contributing_factors": ["memory_leak"],
        })
        # service match (+3) + factors overlap (+2) = 5, above threshold
        assert len(matches) == 1
        assert matches[0]["match_score"] == 5

    def test_extract_pattern(self):
        incident = {
            "incident_id": "INC-001",
            "source_service": "inventory",
            "detection_class": "synthetic",
            "severity": "sev2",
            "contributing_factors": ["slow_query"],
            "affected_services": ["orders", "gateway"],
        }
        pattern = self.matcher.extract_pattern(incident)
        assert pattern["service"] == "inventory"
        assert pattern["created_from"] == "INC-001"
        assert len(self.matcher._patterns) == 1

    def test_recurrence_rate_zero_when_no_matches(self):
        self.matcher.register_pattern({"service": "a"})
        self.matcher.register_pattern({"service": "b"})
        assert self.matcher.get_recurrence_rate() == 0.0

    def test_recurrence_rate_with_matched_patterns(self):
        self.matcher._patterns = [
            {"service": "a", "_match_count": 2},
            {"service": "b", "_match_count": 0},
        ]
        assert self.matcher.get_recurrence_rate() == 50.0


class TestActionTracker:
    def setup_method(self):
        self.tracker = ActionTracker()

    def test_add_and_retrieve(self):
        item = ActionItem(
            action_id="ACT-001",
            incident_id="INC-001",
            title="Fix detection",
            pillar="detection",
        )
        self.tracker.add(item)
        assert len(self.tracker._items) == 1
        assert self.tracker._items["ACT-001"].title == "Fix detection"

    def test_complete_action(self):
        item = ActionItem(action_id="ACT-002", incident_id="INC-001", title="Test")
        self.tracker.add(item)
        result = self.tracker.complete("ACT-002")
        assert result is True
        assert self.tracker._items["ACT-002"].status == "completed"
        assert self.tracker._items["ACT-002"].completed_at is not None

    def test_complete_nonexistent_returns_false(self):
        assert self.tracker.complete("ACT-MISSING") is False

    def test_complete_already_completed_returns_false(self):
        item = ActionItem(action_id="ACT-003", status="completed")
        self.tracker.add(item)
        assert self.tracker.complete("ACT-003") is False

    def test_get_open_items(self):
        self.tracker.add(ActionItem(action_id="A1", status="open"))
        self.tracker.add(ActionItem(action_id="A2", status="completed"))
        self.tracker.add(ActionItem(action_id="A3", status="open"))
        assert len(self.tracker.get_open_items()) == 2

    def test_get_overdue_items(self):
        overdue = ActionItem(action_id="A1", due_date=time.time() - 100, status="open")
        not_overdue = ActionItem(action_id="A2", due_date=time.time() + 3600, status="open")
        self.tracker.add(overdue)
        self.tracker.add(not_overdue)
        result = self.tracker.get_overdue_items()
        assert len(result) == 1
        assert result[0].action_id == "A1"

    def test_get_by_pillar(self):
        self.tracker.add(ActionItem(action_id="A1", pillar="detection"))
        self.tracker.add(ActionItem(action_id="A2", pillar="recovery"))
        self.tracker.add(ActionItem(action_id="A3", pillar="detection"))
        assert len(self.tracker.get_by_pillar("detection")) == 2
        assert len(self.tracker.get_by_pillar("recovery")) == 1
        assert len(self.tracker.get_by_pillar("evolution")) == 0

    def test_stats(self):
        self.tracker.add(ActionItem(action_id="A1", pillar="detection", status="open"))
        self.tracker.add(ActionItem(action_id="A2", pillar="recovery", status="open"))
        self.tracker.complete("A1")
        stats = self.tracker.get_stats()
        assert stats["total"] == 2
        assert stats["completed"] == 1
        assert stats["open"] == 1
        assert stats["completion_rate"] == 50.0
        assert stats["by_pillar"]["detection"] == 1

    def test_stats_empty(self):
        stats = self.tracker.get_stats()
        assert stats["total"] == 0
        assert stats["completion_rate"] == 0


class TestKnowledgeBase:
    def setup_method(self):
        self.kb = KnowledgeBase()

    def test_store_and_search(self):
        incident = {"incident_id": "INC-001", "source_service": "payments", "severity": "sev1"}
        review = {"contributing_factors": [{"factor": "timeout"}], "lessons_learned": ["Add retries"]}
        self.kb.store_incident(incident, review)
        assert self.kb.size == 1
        results = self.kb.search(service="payments")
        assert len(results) == 1
        assert results[0]["incident_id"] == "INC-001"

    def test_search_by_severity(self):
        self.kb.store_incident(
            {"incident_id": "I1", "source_service": "a", "severity": "sev1"},
            {"lessons_learned": []},
        )
        self.kb.store_incident(
            {"incident_id": "I2", "source_service": "b", "severity": "sev3"},
            {"lessons_learned": []},
        )
        assert len(self.kb.search(severity="sev1")) == 1
        assert len(self.kb.search(severity="sev3")) == 1
        assert len(self.kb.search(severity="sev4")) == 0

    def test_search_combined_filters(self):
        self.kb.store_incident(
            {"incident_id": "I1", "source_service": "payments", "severity": "sev1"},
            {"lessons_learned": []},
        )
        self.kb.store_incident(
            {"incident_id": "I2", "source_service": "payments", "severity": "sev3"},
            {"lessons_learned": []},
        )
        assert len(self.kb.search(service="payments", severity="sev1")) == 1

    def test_get_lessons_for_service(self):
        self.kb.store_incident(
            {"incident_id": "I1", "source_service": "orders"},
            {"lessons_learned": ["Lesson A", "Lesson B"]},
        )
        self.kb.store_incident(
            {"incident_id": "I2", "source_service": "orders"},
            {"lessons_learned": ["Lesson C"]},
        )
        self.kb.store_incident(
            {"incident_id": "I3", "source_service": "gateway"},
            {"lessons_learned": ["Lesson D"]},
        )
        lessons = self.kb.get_lessons_for_service("orders")
        assert len(lessons) == 3
        assert "Lesson A" in lessons

    def test_empty_search(self):
        assert self.kb.search(service="nonexistent") == []
        assert self.kb.size == 0


class TestPostIncidentReview:
    def setup_method(self):
        self.generator = PostIncidentReviewGenerator()

    def test_generate_review(self):
        incident_data = {
            "incident_id": "INC-001",
            "source_service": "payments",
            "severity": "sev1",
            "time_to_detect": 120,
            "time_to_recover": 600,
            "blast_radius": {"containment_pct": 98},
            "affected_services": ["payments"],
        }
        review = self.generator.generate(incident_data, [])
        assert review["incident_id"] == "INC-001"
        assert review["severity"] == "sev1"
        assert "blameless_note" in review
        assert review["mttd"] == 120

    def test_detection_effectiveness_fast(self):
        data = {"time_to_detect": 0}
        assert self.generator._compute_detection_effectiveness(data) == 1.0

    def test_detection_effectiveness_slow(self):
        data = {"time_to_detect": 600}
        assert self.generator._compute_detection_effectiveness(data) == 0.0

    def test_detection_effectiveness_mid(self):
        data = {"time_to_detect": 300}
        assert self.generator._compute_detection_effectiveness(data) == pytest.approx(0.5)

    def test_contributing_factors_delayed_detection(self):
        data = {"time_to_detect": 400, "affected_services": []}
        factors = self.generator._analyze_contributing_factors(data, [])
        factor_names = [f["factor"] for f in factors]
        assert "Delayed detection" in factor_names

    def test_contributing_factors_blast_radius(self):
        data = {"time_to_detect": 60, "affected_services": ["a", "b", "c"]}
        factors = self.generator._analyze_contributing_factors(data, [])
        factor_names = [f["factor"] for f in factors]
        assert "Insufficient blast radius containment" in factor_names

    def test_response_assessment_effective(self):
        data = {
            "time_to_detect": 60,
            "time_to_recover": 300,
            "blast_radius": {"containment_pct": 99},
        }
        adaptation_event = Event(
            category=EventCategory.ADAPTATION,
            event_type="scaling_triggered",
            source="test",
        )
        response = self.generator._assess_response(data, [adaptation_event])
        assert response["detection"] == "effective"
        assert response["recovery"] == "effective"
        assert response["absorption"] == "effective"
        assert response["adaptation"] == "effective"

    def test_response_assessment_needs_improvement(self):
        data = {
            "time_to_detect": 500,
            "time_to_recover": 1200,
            "blast_radius": {"containment_pct": 80},
        }
        response = self.generator._assess_response(data, [])
        assert response["detection"] == "needs_improvement"
        assert response["recovery"] == "needs_improvement"
        assert response["adaptation"] == "needs_improvement"

    def test_adaptation_latency_calculation(self):
        now = time.time()
        detection = Event(
            category=EventCategory.DETECTION,
            event_type="alert",
            source="test",
        )
        detection.timestamp = now

        adaptation = Event(
            category=EventCategory.ADAPTATION,
            event_type="scaling",
            source="test",
        )
        adaptation.timestamp = now + 15.0

        latency = self.generator._compute_adaptation_latency([detection, adaptation])
        assert latency == pytest.approx(15.0)

    def test_lessons_within_targets(self):
        data = {"time_to_detect": 60, "time_to_recover": 300}
        adaptation_event = Event(
            category=EventCategory.ADAPTATION,
            event_type="scaling",
            source="test",
        )
        lessons = self.generator._extract_lessons(data, [adaptation_event])
        assert any("what went well" in l for l in lessons)
