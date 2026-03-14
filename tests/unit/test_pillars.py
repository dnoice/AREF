"""
Tests for AREF pillar implementations.
"""

import asyncio
import time

import pytest

from aref.core.events import EventSeverity

# Detection
from aref.detection.threshold import ThresholdDetector, ThresholdRule
from aref.detection.anomaly import AnomalyDetector, MetricStream
from aref.detection.sli_tracker import SLITracker, SLI, SLO, ErrorBudget

# Absorption
from aref.absorption.circuit_breaker import CircuitBreaker, CircuitState, CircuitBreakerError
from aref.absorption.rate_limiter import TokenBucket, RateLimitExceeded
from aref.absorption.bulkhead import Bulkhead, BulkheadFullError
from aref.absorption.blast_radius import BlastRadiusAnalyzer, DependencyNode

# Adaptation
from aref.adaptation.feature_flags import FeatureFlagManager, FeatureFlag
from aref.adaptation.decision_tree import AdaptationDecisionTree
from aref.core.models import AnomalyClass

# Maturity
from aref.maturity.model import MaturityAssessor
from aref.core.config import RiskProfile


class TestThresholdDetector:
    @pytest.mark.asyncio
    async def test_threshold_breach(self):
        detector = ThresholdDetector()
        current_cpu = [95.0]

        detector.add_rule(ThresholdRule(
            name="cpu_usage",
            service="orders",
            metric_fn=lambda: current_cpu[0],
            warning_threshold=80.0,
            critical_threshold=90.0,
            consecutive_samples=1,
        ))

        violations = await detector.check_all()
        assert len(violations) == 1
        assert violations[0]["severity"] == EventSeverity.CRITICAL

    @pytest.mark.asyncio
    async def test_no_breach(self):
        detector = ThresholdDetector()
        detector.add_rule(ThresholdRule(
            name="cpu_usage",
            service="orders",
            metric_fn=lambda: 50.0,
            warning_threshold=80.0,
            critical_threshold=90.0,
            consecutive_samples=1,
        ))

        violations = await detector.check_all()
        assert len(violations) == 0


class TestAnomalyDetector:
    @pytest.mark.asyncio
    async def test_z_score_anomaly(self):
        detector = AnomalyDetector()
        stream = MetricStream(name="latency", service="orders", z_score_threshold=3.0)

        # Record normal values
        for i in range(50):
            stream.record(100.0 + (i % 5))

        # Record anomalous value (way above mean)
        stream.record(500.0)

        detector.register_stream(stream)
        anomalies = await detector.detect()
        assert len(anomalies) == 1
        assert anomalies[0]["z_score"] > 3.0


class TestSLITracker:
    def test_error_budget_computation(self):
        slo = SLO(name="availability", sli_name="uptime", service="orders", target=0.999)
        budget = ErrorBudget(slo)

        # 30 days window, 0.1% budget = ~2592 seconds
        assert budget.total_budget == pytest.approx(2592.0, rel=0.01)

        budget.record_downtime(1000)
        assert budget.consumed_pct == pytest.approx(38.58, rel=1)
        assert not budget.is_exhausted

        budget.record_downtime(2000)
        assert budget.is_exhausted


class TestCircuitBreaker:
    @pytest.mark.asyncio
    async def test_circuit_opens_on_failures(self):
        cb = CircuitBreaker(
            name="test", service="orders", dependency="payments",
            failure_threshold=3, recovery_timeout=1.0,
        )

        async def failing():
            raise Exception("fail")

        for _ in range(3):
            with pytest.raises(Exception):
                await cb.call(failing)

        assert cb.state == CircuitState.OPEN

        with pytest.raises(CircuitBreakerError):
            await cb.call(failing)

    @pytest.mark.asyncio
    async def test_circuit_recovers(self):
        cb = CircuitBreaker(
            name="test", service="orders", dependency="payments",
            failure_threshold=2, recovery_timeout=0.1, half_open_max_calls=1,
        )

        async def failing():
            raise Exception("fail")

        async def succeeding():
            return "ok"

        # Open the breaker
        for _ in range(2):
            with pytest.raises(Exception):
                await cb.call(failing)

        assert cb.state == CircuitState.OPEN

        # Wait for recovery timeout
        await asyncio.sleep(0.15)

        # Should be half-open now
        assert cb.state == CircuitState.HALF_OPEN

        # Successful call should close it
        result = await cb.call(succeeding)
        assert result == "ok"
        assert cb.state == CircuitState.CLOSED


class TestRateLimiter:
    def test_token_bucket(self):
        bucket = TokenBucket(name="test", rate=10.0, capacity=5)

        # Should allow burst of 5
        for _ in range(5):
            assert bucket.allow()

        # 6th should be rejected (no time to refill)
        assert not bucket.allow()

    def test_rate_limit_exceeded(self):
        bucket = TokenBucket(name="test", rate=1.0, capacity=1)
        bucket.consume()  # First should pass

        with pytest.raises(RateLimitExceeded):
            bucket.consume()


class TestBulkhead:
    @pytest.mark.asyncio
    async def test_concurrent_limit(self):
        bulkhead = Bulkhead(name="test", max_concurrent=2, max_queue=1, timeout=1.0)
        entered = asyncio.Event()

        async def slow_task():
            entered.set()
            await asyncio.sleep(1.0)
            return "done"

        # Start 2 tasks that will hold the semaphore
        task1 = asyncio.create_task(bulkhead.execute(slow_task))
        await entered.wait()
        entered.clear()
        task2 = asyncio.create_task(bulkhead.execute(slow_task))
        await entered.wait()

        # Both slots occupied. One more can queue (max_queue=1)
        # But a 4th should be rejected
        task3 = asyncio.create_task(bulkhead.execute(slow_task))
        await asyncio.sleep(0.01)  # let it enqueue

        with pytest.raises(BulkheadFullError):
            await bulkhead.execute(slow_task)

        task1.cancel()
        task2.cancel()
        task3.cancel()
        # Suppress cancellation errors
        for t in [task1, task2, task3]:
            try:
                await t
            except (asyncio.CancelledError, BulkheadFullError):
                pass


class TestBlastRadius:
    def test_dependency_analysis(self):
        analyzer = BlastRadiusAnalyzer()

        analyzer.register_node(DependencyNode(name="gateway", dependents=[], dependencies=["orders"]))
        analyzer.register_node(DependencyNode(name="orders", dependents=["gateway"], dependencies=["payments", "inventory"]))
        analyzer.register_node(DependencyNode(name="payments", dependents=["orders"], dependencies=[]))
        analyzer.register_node(DependencyNode(name="inventory", dependents=["orders"], dependencies=[]))
        analyzer.register_node(DependencyNode(name="notifications", dependents=["orders"], dependencies=[]))

        # Register dependencies
        analyzer.register_dependency("gateway", "orders")
        analyzer.register_dependency("orders", "payments")
        analyzer.register_dependency("orders", "inventory")

        # Analyze: payments failure
        assessment = analyzer.analyze("payments", incident_id="INC-TEST")
        assert "orders" in assessment.directly_affected


class TestFeatureFlags:
    def test_shed_non_critical(self):
        mgr = FeatureFlagManager()
        mgr.register(FeatureFlag(name="recommendations", service="orders", critical=False))
        mgr.register(FeatureFlag(name="notifications", service="orders", critical=False))
        mgr.register(FeatureFlag(name="checkout", service="orders", critical=True))

        shed = mgr.shed_non_critical(service="orders")
        assert len(shed) == 2
        assert mgr.is_enabled("checkout")
        assert not mgr.is_enabled("recommendations")


class TestDecisionTree:
    def test_transient_warning(self):
        tree = AdaptationDecisionTree()
        action = tree.decide(
            anomaly_class=AnomalyClass.TRANSIENT,
            severity=EventSeverity.WARNING,
            service="orders",
        )
        assert action is not None
        assert action.strategy == "horizontal_scaling"

    def test_escalating_triggers_feature_flags(self):
        tree = AdaptationDecisionTree()
        action = tree.decide(
            anomaly_class=AnomalyClass.ESCALATING,
            severity=EventSeverity.EMERGENCY,
            service="orders",
        )
        assert action is not None
        assert action.strategy == "feature_flagging"


class TestMaturityAssessor:
    def test_assessment(self):
        assessor = MaturityAssessor()
        context = {
            "detection": {"sli_count": 5, "anomaly_detection": True, "mttd": 180},
            "absorption": {"circuit_breakers": 3, "containment_pct": 85},
            "adaptation": {"auto_scaling": True, "feature_flags": 8, "adaptation_latency": 25},
            "recovery": {"runbook_count": 5, "drills_per_year": 4, "mttr": 600},
            "evolution": {"review_count": 3, "action_completion_rate": 80, "actions_per_quarter": 6},
        }
        report = assessor.assess(context)

        assert len(report.assessments) == 5
        assert all(a.score >= 1.0 for a in report.assessments.values())
        assert len(report.crs_scores) == len(RiskProfile)
        assert report.crs_scores["balanced"] > 0
