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
    mcp_insecure_localhost: bool = False
    """Disable MCP DNS-rebinding Host/Origin validation entirely.

    Defaults to safe: validation is on, restricted to localhost/127.0.0.1.
    Setting ``BRANCHPOINT_MCP_INSECURE_LOCALHOST=true`` turns it off — an
    explicit opt-in, never the default.
    """
    demo_scenario_path: str | None = None
    """Override path to the hero scenario fixture (``BRANCHPOINT_DEMO_SCENARIO_PATH``).

    Unset by default: the demo engine loads the fixture packaged inside
    ``app.infrastructure.demo``, which works regardless of how the package was
    installed. Set this only to point at a different scenario file.
    """

    @property
    def is_production(self) -> bool:
        """Whether this process is configured as a production environment.

        Destructive demo-only surfaces (state reset) must check this before
        exposing anything that discards the current demo scenario.
        """
        return self.env.strip().lower() == "production"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide validated settings instance."""
    return Settings()
