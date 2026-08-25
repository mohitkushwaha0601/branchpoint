"""Loads the deterministic hero scenario fixture into typed demo state."""

import json
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

#: The repository root is two levels above this file's package (backend/).
DEFAULT_SCENARIO_PATH = (
    Path(__file__).resolve().parents[3] / "scenarios" / "checkout_regression.json"
)


def load_initial_state(path: Path = DEFAULT_SCENARIO_PATH) -> DemoProductionState:
    """Parse the hero scenario fixture into a validated :class:`DemoProductionState`.

    Raises if the fixture is missing or fails validation — a broken fixture
    must never silently produce an empty or partial reality.
    """
    raw = json.loads(path.read_text())
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
