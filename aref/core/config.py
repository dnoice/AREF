"""
Centralized configuration for the AREF platform.
Uses pydantic-settings for env-driven, validated config with sensible defaults.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RiskProfile(str, Enum):
    AVAILABILITY_CRITICAL = "availability_critical"
    DATA_INTEGRITY_CRITICAL = "data_integrity_critical"
    BALANCED = "balanced"
    INNOVATION_HEAVY = "innovation_heavy"


# CRS weight profiles straight from the blueprint (Section 6.3)
CRS_WEIGHT_PROFILES: dict[RiskProfile, dict[str, float]] = {
    RiskProfile.AVAILABILITY_CRITICAL: {
        "detection": 0.30, "absorption": 0.25, "adaptation": 0.20,
        "recovery": 0.15, "evolution": 0.10,
    },
    RiskProfile.DATA_INTEGRITY_CRITICAL: {
        "detection": 0.20, "absorption": 0.20, "adaptation": 0.15,
        "recovery": 0.30, "evolution": 0.15,
    },
    RiskProfile.BALANCED: {
        "detection": 0.20, "absorption": 0.20, "adaptation": 0.20,
        "recovery": 0.20, "evolution": 0.20,
    },
    RiskProfile.INNOVATION_HEAVY: {
        "detection": 0.15, "absorption": 0.15, "adaptation": 0.25,
        "recovery": 0.15, "evolution": 0.30,
    },
}


class DatabaseConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AREF_DB_")

    host: str = "localhost"
    port: int = 5432
    name: str = "aref"
    user: str = "aref"
    password: str = "aref_secret"
    pool_min: int = 2
    pool_max: int = 10

    @property
    def dsn(self) -> str:
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"

    @property
    def sync_dsn(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


class RedisConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AREF_REDIS_")

    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str | None = None

    @property
    def url(self) -> str:
        auth = f":{self.password}@" if self.password else ""
        return f"redis://{auth}{self.host}:{self.port}/{self.db}"


class DetectionConfig(BaseSettings):
    """Pillar I thresholds — aligned with blueprint Section 3.1."""
    model_config = SettingsConfigDict(env_prefix="AREF_DETECTION_")

    mttd_target_seconds: float = 300.0  # < 5 minutes
    threshold_check_interval: float = 10.0
    anomaly_check_interval: float = 30.0
    synthetic_probe_interval: float = 15.0
    change_correlation_window: float = 600.0  # 10 minutes
    alert_fatigue_max_per_week: int = 50
    alert_to_action_ratio: float = 3.0  # 3:1 per blueprint


class AbsorptionConfig(BaseSettings):
    """Pillar II thresholds — aligned with blueprint Section 3.2."""
    model_config = SettingsConfigDict(env_prefix="AREF_ABSORPTION_")

    blast_radius_target_pct: float = 95.0  # > 95%
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_timeout: float = 30.0
    circuit_breaker_half_open_max: int = 3
    bulkhead_max_concurrent: int = 50
    rate_limit_requests_per_second: float = 100.0
    rate_limit_burst: int = 20


class AdaptationConfig(BaseSettings):
    """Pillar III thresholds — aligned with blueprint Section 3.3."""
    model_config = SettingsConfigDict(env_prefix="AREF_ADAPTATION_")

    latency_target_seconds: float = 30.0  # < 30 seconds
    scale_up_cpu_threshold: float = 80.0
    scale_down_cpu_threshold: float = 30.0
    traffic_shift_health_threshold: float = 0.7
    feature_flag_error_budget_trigger: float = 0.5  # 50% budget consumed
    adaptation_window_seconds: float = 120.0  # escalate to recovery after this


class RecoveryConfig(BaseSettings):
    """Pillar IV thresholds — aligned with blueprint Section 3.4."""
    model_config = SettingsConfigDict(env_prefix="AREF_RECOVERY_")

    mttr_target_seconds: float = 900.0  # < 15 minutes
    t0_target_seconds: float = 300.0    # 0-5 min
    t1_target_seconds: float = 900.0    # 5-15 min
    t2_target_seconds: float = 3600.0   # 15-60 min
    t3_target_seconds: float = 14400.0  # 1-4 hours
    t4_target_days: int = 14            # 1-2 weeks
    runbook_drill_interval_days: int = 90  # quarterly


class EvolutionConfig(BaseSettings):
    """Pillar V thresholds — aligned with blueprint Section 3.5."""
    model_config = SettingsConfigDict(env_prefix="AREF_EVOLUTION_")

    improvement_velocity_target: int = 8  # > 8 actions/quarter
    action_completion_rate_target: float = 85.0  # > 85%
    recurrence_rate_target: float = 10.0  # < 10%
    knowledge_share_target_hours: float = 72.0  # < 72 hours
    post_incident_review_deadline_hours: float = 72.0


class AREFConfig(BaseSettings):
    """Root configuration — aggregates all pillar configs."""
    model_config = SettingsConfigDict(env_prefix="AREF_")

    environment: str = "development"
    debug: bool = True
    log_level: str = "INFO"
    risk_profile: RiskProfile = RiskProfile.BALANCED
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    dashboard_port: int = 8080

    db: DatabaseConfig = Field(default_factory=DatabaseConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    detection: DetectionConfig = Field(default_factory=DetectionConfig)
    absorption: AbsorptionConfig = Field(default_factory=AbsorptionConfig)
    adaptation: AdaptationConfig = Field(default_factory=AdaptationConfig)
    recovery: RecoveryConfig = Field(default_factory=RecoveryConfig)
    evolution: EvolutionConfig = Field(default_factory=EvolutionConfig)

    @property
    def crs_weights(self) -> dict[str, float]:
        return CRS_WEIGHT_PROFILES[self.risk_profile]


# Singleton access
_config: AREFConfig | None = None


def get_config() -> AREFConfig:
    global _config
    if _config is None:
        _config = AREFConfig()
    return _config


def reset_config() -> None:
    global _config
    _config = None
