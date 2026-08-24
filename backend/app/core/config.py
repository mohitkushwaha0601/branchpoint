"""Environment-backed application configuration."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

APP_NAME = "BRANCHPOINT"
APP_VERSION = "0.1.0"
SERVICE_NAME = "branchpoint-backend"


class Settings(BaseSettings):
    """Runtime settings loaded from BRANCHPOINT-prefixed variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="BRANCHPOINT_",
        extra="ignore",
    )

    env: str = "development"
    log_level: Literal["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"] = "INFO"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide validated settings instance."""
    return Settings()
