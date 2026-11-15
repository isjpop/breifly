"""Application configuration loaded from environment variables.

All configuration lives here so no other module reads ``os.environ`` directly.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # The repo-root .env (shared with Docker Compose) is read when running from backend/;
    # a backend/.env, if present, overrides it. Real environment variables override both.
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"

    database_url: str = Field(
        default="postgresql+psycopg://briefly:briefly@localhost:5432/briefly",
        description="SQLAlchemy URL for PostgreSQL.",
    )
    database_pool_size: int = Field(default=5, ge=1)
    database_echo: bool = False

    # --- Ingestion ---
    ingestion_interval_minutes: int = Field(default=15, ge=1)
    ingestion_user_agent: str = "BrieflyBot/0.1 (+news aggregator; RSS reader)"
    http_timeout_seconds: float = Field(default=15.0, gt=0)
    http_max_retries: int = Field(default=3, ge=0, le=10)
    http_backoff_base_seconds: float = Field(default=1.0, ge=0)
    http_backoff_max_seconds: float = Field(default=30.0, ge=0)
    feed_max_bytes: int = Field(default=5_000_000, ge=10_000)
    feed_max_entries: int = Field(default=100, ge=1)
    dedup_lookback_hours: int = Field(default=72, ge=1)

    # --- AI summarization (Gemini) ---
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_api_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_api_revision: str = "2026-05-20"
    llm_timeout_seconds: float = Field(default=45.0, gt=0)
    llm_max_retries: int = Field(default=2, ge=0, le=5)
    llm_max_output_tokens: int = Field(default=1024, ge=256)
    # Client-side throttle; keep at or below your plan's requests-per-minute limit.
    llm_requests_per_minute: float = Field(default=10.0, gt=0)
    # Upper bound on summarization calls per worker tick (cost and quota control).
    llm_max_summaries_per_run: int = Field(default=40, ge=0)
    llm_max_input_chars: int = Field(default=12_000, ge=1_000)
    summary_max_attempts: int = Field(default=3, ge=1)
    # USD per 1M tokens, for usage estimates. Defaults are the paid list price of the default
    # model; actual spend is $0 on the free tier.
    llm_input_cost_per_million: float = Field(default=0.30, ge=0)
    llm_output_cost_per_million: float = Field(default=2.50, ge=0)

    # --- Importance ranking (weights must sum to 1) ---
    ranking_weight_impact: float = Field(default=0.35, ge=0, le=1)
    ranking_weight_significance: float = Field(default=0.30, ge=0, le=1)
    ranking_weight_credibility: float = Field(default=0.20, ge=0, le=1)
    ranking_weight_recency: float = Field(default=0.15, ge=0, le=1)
    ranking_recency_half_life_hours: float = Field(default=12.0, gt=0)
    ranking_refresh_window_hours: int = Field(default=72, ge=1)
    processing_batch_size: int = Field(default=200, ge=1)

    @model_validator(mode="after")
    def ranking_weights_sum_to_one(self) -> "Settings":
        total = (
            self.ranking_weight_impact
            + self.ranking_weight_significance
            + self.ranking_weight_credibility
            + self.ranking_weight_recency
        )
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"ranking weights must sum to 1.0 (got {total:.3f})")
        return self

    @property
    def ai_enabled(self) -> bool:
        return bool(self.gemini_api_key and self.gemini_api_key.get_secret_value().strip())

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, value: str) -> str:
        """Accept plain ``postgres://`` / ``postgresql://`` URLs (as most hosts provide them)
        and route them through the psycopg v3 driver."""
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value[len(prefix) :]
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
