"""Demo state: initial incident, deterministic reset, deterministic metrics."""

import pytest

from app.domain.actions.models import ActionType, RiskClass
from app.infrastructure.demo.engine import DemoProductionEngine, UnknownWorldError
from app.infrastructure.demo.metrics import compute_metrics
from app.infrastructure.demo.scenario import load_initial_state


async def test_initial_reality_reproduces_the_checkout_incident() -> None:
    engine = DemoProductionEngine()
    state = await engine.reality()
    metrics = compute_metrics(state)

    assert state.pricing_deployment.version == "v2.41"
    assert state.pricing_flag.enabled is True
    assert state.pricing_capacity.replicas == 4
    assert metrics.checkout_error_rate == pytest.approx(0.413, abs=1e-9)
    assert metrics.checkout_p95_ms == pytest.approx(4800.0)
    assert metrics.affected_users == pytest.approx(8000, abs=50)


async def test_reset_restores_the_exact_initial_state() -> None:
    engine = DemoProductionEngine()
    initial = await engine.reality()

    await engine.snapshot_world("world_1")
    import sys

    sys.path.insert(0, "tests")
    from factories import make_action

    await engine.apply_to_world(
        "world_1",
        make_action(
            "a1",
            action_type=ActionType.FEATURE_FLAG_DISABLE,
            parameters={"flag_key": "PRICING_V2"},
            risk_class=RiskClass.LOW,
        ),
    )

    restored = await engine.reset()

    assert restored == initial
    assert restored == load_initial_state()


async def test_reset_discards_every_world_snapshot() -> None:
    engine = DemoProductionEngine()
    await engine.snapshot_world("world_1")
    assert await engine.world_state("world_1") is not None

    await engine.reset()

    with pytest.raises(UnknownWorldError):
        await engine.world_state("world_1")


async def test_identical_state_produces_identical_metrics() -> None:
    state_a = load_initial_state()
    state_b = load_initial_state()

    assert state_a == state_b
    assert compute_metrics(state_a) == compute_metrics(state_b)
