"""Environment-backed application configuration."""

from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

APP_NAME = "BRANCHPOINT"
SERVICE_NAME = "branchpoint-backend"

try:
    APP_VERSION = version(SERVICE_NAME)
except PackageNotFoundError:
    # The checkout is not installed into the environment; run `uv sync` from backend/.
    APP_VERSION = "0.0.0"


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
