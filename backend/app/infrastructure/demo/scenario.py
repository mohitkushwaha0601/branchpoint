"""Loads the deterministic hero scenario fixture into typed demo state."""

import json
from importlib.resources import files
from pathlib import Path

from app.infrastructure.demo.state import (
    CheckoutCapacity,
    DatabaseState,
    DemoProductionState,
    FeatureFlagState,
    OrderRecord,
    ServiceCapacity,
    ServiceDeployment,
)

#: Fixture bundled inside the package (app/infrastructure/demo/scenarios/), so
#: uv_build includes it in every wheel regardless of install layout — unlike a
#: path built from ``__file__.parents[N]``, which only resolves inside a repo
#: checkout with this exact directory structure.
PACKAGED_SCENARIO_RESOURCE = files("app.infrastructure.demo.scenarios") / "checkout_regression.json"

#: Env var (``BRANCHPOINT_DEMO_SCENARIO_PATH`` via ``Settings.demo_scenario_path``)
#: that, when set, overrides the packaged fixture with a file on disk.
DEMO_SCENARIO_PATH_ENV_VAR = "BRANCHPOINT_DEMO_SCENARIO_PATH"


def _default_scenario_source() -> Path:
    """Return the fixture to load: an explicit env override, or the packaged one."""
    from app.core.config import get_settings

    override = get_settings().demo_scenario_path
    if override:
        return Path(override)
    return PACKAGED_SCENARIO_RESOURCE


def load_initial_state(path: Path | None = None) -> DemoProductionState:
    """Parse the hero scenario fixture into a validated :class:`DemoProductionState`.

    ``path`` defaults to the packaged fixture, or the path named by
    ``BRANCHPOINT_DEMO_SCENARIO_PATH`` if that's set. Raises with a clear,
    actionable message if the fixture is missing or fails validation — a
    broken fixture must never silently produce an empty or partial reality.
    """
    source = path if path is not None else _default_scenario_source()
    try:
        raw = json.loads(source.read_text())
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"demo scenario fixture not found at {source}. "
            f"This ships inside the package by default; if you set "
            f"{DEMO_SCENARIO_PATH_ENV_VAR}, check that path is correct."
        ) from exc

    return DemoProductionState(
        snapshot_at=raw["snapshot_at"],
        orders_schema_version=raw["orders_schema_version"],
        pricing_deployment=ServiceDeployment(**raw["pricing_deployment"]),
        pricing_flag=FeatureFlagState(**raw["pricing_flag"]),
        pricing_capacity=ServiceCapacity(**raw["pricing_capacity"]),
        database=DatabaseState(**raw["database"]),
        checkout_capacity=CheckoutCapacity(**raw["checkout_capacity"]),
        orders=tuple(OrderRecord(**order) for order in raw["orders"]),
    )
