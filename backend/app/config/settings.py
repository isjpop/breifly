"""Application configuration loaded from environment variables.

All configuration lives here so no other module reads ``os.environ`` directly.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"

    database_url: str = Field(
        default="postgresql+psycopg://briefly:briefly@localhost:5432/briefly",
        description="SQLAlchemy URL for PostgreSQL.",
    )
    database_pool_size: int = Field(default=5, ge=1)
    database_echo: bool = False

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
