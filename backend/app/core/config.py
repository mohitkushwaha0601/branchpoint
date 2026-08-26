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


class ModelNotConfiguredError(RuntimeError):
    """Raised when no model FQN is configured for BRANCHPOINT's agents."""

    def __init__(self) -> None:
        super().__init__(
            "no model configured; set BRANCHPOINT_MODEL to a fully-qualified model name "
            "that TrueForge has a provider for (e.g. anthropic/claude-sonnet-4-5). "
            "The provider's API key belongs in TrueForge, never in BRANCHPOINT."
        )


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
    trueforge_base_url: str = "http://localhost:8790"
    """Base URL of the TrueForge harness (``BRANCHPOINT_TRUEFORGE_BASE_URL``)."""
    model: str = ""
    """The one model every BRANCHPOINT agent runs on (``BRANCHPOINT_MODEL``).

    A fully-qualified name TrueForge understands, e.g. ``anthropic/claude-sonnet-4-5``.
    BRANCHPOINT treats the string as **opaque**: it is never parsed, split on
    ``/``, or checked against a provider list — whatever is configured here is
    handed to TrueForge verbatim.

    Empty by default: BRANCHPOINT never hardwires a provider, and holds no
    model credentials. The provider's API key lives in TrueForge.

    There is deliberately no per-role model variable. Planner and DOPPELGÄNGER
    resolve the same string, so a run cannot silently mix models.
    """
    trueforge_model: str = ""
    """Deprecated alias for :attr:`model` (``BRANCHPOINT_TRUEFORGE_MODEL``).

    Still honoured so existing deployments keep working, but only when
    ``BRANCHPOINT_MODEL`` is unset. Resolution order lives in
    :meth:`resolve_model`.
    """
    trueforge_mcp_server_name: str = "branchpoint"
    """Name BRANCHPOINT is registered under in TrueForge's MCP settings."""
    trueforge_mcp_url: str = "http://127.0.0.1:8000/mcp"
    """URL TrueForge should reach this backend's MCP server on."""
    trueforge_sandbox_enabled: bool = False
    """Whether DOPPELGÄNGER sessions get a TrueForge sandbox for exploration.

    Off unless ``BRANCHPOINT_TRUEFORGE_SANDBOX_ENABLED`` says otherwise. Code
    execution is opt-in: a deployment that never sets the variable — no ``.env``
    file, no exported variable — gets no sandbox, rather than one nobody asked
    for. That is also the fail-closed reading, since an unreachable sandbox
    provider aborts an adversarial turn.

    DOPPELGÄNGER only. The planner and the commit operator are hardwired to
    ``sandbox.enabled = false`` and do not consult this setting: nothing that
    reads reality or writes to it is ever given code execution.

    Turning it on grants exploratory ``exec`` inside the sandbox and nothing
    else — no extra tools, and no path to a veto. Sandbox output is recorded
    with ``machine_verifiable=False``; only BRANCHPOINT's own replay can produce
    the machine-verifiable failing evidence a veto requires.
    """

    trueforge_skill_name: str = ""
    """Name of a TrueForge Skill to mount on DOPPELGÄNGER sessions.

    Empty by default, and empty means the agent spec carries no ``skills`` key
    at all — the hero path is exactly what it was.

    It is opt-in because a skill is registered with TrueForge *out of band*
    (``PUT /api/v1/settings/skills`` with a git manifest) and referenced here by
    name. Naming a skill TrueForge has not been given makes the turn
    unprocessable, which is the one place a failure is least affordable.
    Register the skill first, confirm it, then set this.

    A mounted skill also needs a sandbox: TrueForge materialises skills in the
    sandbox working directory, so set this only alongside
    ``BRANCHPOINT_TRUEFORGE_SANDBOX_ENABLED``. Nothing enforces the pairing here
    — a guard would be this codebase asserting third-party behaviour it cannot
    verify offline — so it is documented rather than checked.

    See ``trueforge/skills/incident-counterfactual-review/SKILL.md``.
    """

    cors_allow_origins: str = ""
    """Comma-separated browser origins allowed to call this API.

    Empty by default, which installs no CORS middleware at all: local
    development goes through the Vite dev-server proxy, so the browser only ever
    talks to its own origin and CORS never enters the picture.

    Set this only for a deployed frontend on a different origin, and set it to
    exact origins — ``https://branchpoint.vercel.app``, never ``*``. Credentials
    are never enabled, so a wildcard could not be combined with them anyway.
    """

    demo_scenario_path: str | None = None
    """Override path to the hero scenario fixture (``BRANCHPOINT_DEMO_SCENARIO_PATH``).

    Unset by default: the demo engine loads the fixture packaged inside
    ``app.infrastructure.demo``, which works regardless of how the package was
    installed. Set this only to point at a different scenario file.
    """

    def resolve_cors_origins(self) -> tuple[str, ...]:
        """Return the configured browser origins, trimmed and de-duplicated."""
        seen: dict[str, None] = {}
        for origin in self.cors_allow_origins.split(","):
            trimmed = origin.strip()
            if trimmed:
                seen.setdefault(trimmed, None)
        return tuple(seen)

    def resolve_model(self) -> str:
        """Return the single model FQN every TrueForge-backed agent must use.

        ``BRANCHPOINT_MODEL`` wins; ``BRANCHPOINT_TRUEFORGE_MODEL`` is the
        legacy fallback; neither configured is a configuration error rather
        than a silent default, because guessing a provider on an operator's
        behalf is how a run ends up on a model nobody chose.

        The resolved value is returned as configured (whitespace trimmed only)
        — BRANCHPOINT never interprets it.
        """
        for configured in (self.model, self.trueforge_model):
            resolved = configured.strip()
            if resolved:
                return resolved
        raise ModelNotConfiguredError

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
