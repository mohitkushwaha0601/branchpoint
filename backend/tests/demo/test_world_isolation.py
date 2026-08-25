"""World snapshots are structurally isolated: mutating one never leaks to another."""

import asyncio

from app.domain.actions.models import ActionType, RiskClass
from app.infrastructure.demo.engine import DemoProductionEngine
from tests.factories import make_action

ALPHA = make_action(
    "a1",
    action_type=ActionType.ROLLBACK,
    parameters={"version": "v2.40"},
    risk_class=RiskClass.HIGH,
)
BETA = make_action(
    "b1",
    action_type=ActionType.FEATURE_FLAG_DISABLE,
    parameters={"flag_key": "PRICING_V2"},
    risk_class=RiskClass.LOW,
)
GAMMA = make_action(
    "g1",
    action_type=ActionType.SCALE,
    parameters={"target_replicas": 12},
    risk_class=RiskClass.MEDIUM,
)


async def test_world_snapshots_are_isolated_from_each_other() -> None:
    engine = DemoProductionEngine()
    await engine.snapshot_world("world_alpha")
    await engine.snapshot_world("world_beta")

    alpha = await engine.apply_to_world("world_alpha", ALPHA)
    beta = await engine.world_state("world_beta")

    assert alpha.pricing_deployment.version == "v2.40"
    assert beta.pricing_deployment.version == "v2.41"


async def test_world_mutation_never_changes_reality() -> None:
    engine = DemoProductionEngine()
    reality_before = await engine.reality()

    await engine.snapshot_world("world_alpha")
    await engine.apply_to_world("world_alpha", ALPHA)

    assert await engine.reality() == reality_before


async def test_alpha_mutation_does_not_change_beta_or_gamma() -> None:
    engine = DemoProductionEngine()
    await engine.snapshot_world("world_alpha")
    await engine.snapshot_world("world_beta")
    await engine.snapshot_world("world_gamma")

    await engine.apply_to_world("world_alpha", ALPHA)
    beta = await engine.world_state("world_beta")
    gamma = await engine.world_state("world_gamma")

    assert beta.pricing_deployment.version == "v2.41"
    assert beta.pricing_flag.enabled is True
    assert gamma.pricing_deployment.version == "v2.41"
    assert gamma.pricing_capacity.replicas == 4


async def test_gamma_mutation_does_not_change_alpha_or_beta() -> None:
    engine = DemoProductionEngine()
    await engine.snapshot_world("world_alpha")
    await engine.snapshot_world("world_beta")
    await engine.snapshot_world("world_gamma")

    await engine.apply_to_world("world_gamma", GAMMA)
    alpha = await engine.world_state("world_alpha")
    beta = await engine.world_state("world_beta")

    assert alpha.pricing_capacity.replicas == 4
    assert alpha.pricing_deployment.version == "v2.41"
    assert beta.pricing_capacity.replicas == 4
    assert beta.pricing_flag.enabled is True


async def test_concurrent_world_mutation_leaves_no_cross_world_state_leakage() -> None:
    engine = DemoProductionEngine()
    for world_id in ("world_alpha", "world_beta", "world_gamma"):
        await engine.snapshot_world(world_id)

    await asyncio.gather(
        engine.apply_to_world("world_alpha", ALPHA),
        engine.apply_to_world("world_beta", BETA),
        engine.apply_to_world("world_gamma", GAMMA),
    )

    alpha = await engine.world_state("world_alpha")
    beta = await engine.world_state("world_beta")
    gamma = await engine.world_state("world_gamma")
    reality = await engine.reality()

    assert alpha.pricing_deployment.version == "v2.40"
    assert alpha.pricing_flag.enabled is True
    assert alpha.pricing_capacity.replicas == 4

    assert beta.pricing_deployment.version == "v2.41"
    assert beta.pricing_flag.enabled is False
    assert beta.pricing_capacity.replicas == 4

    assert gamma.pricing_deployment.version == "v2.41"
    assert gamma.pricing_flag.enabled is True
    assert gamma.pricing_capacity.replicas == 12

    assert reality.pricing_deployment.version == "v2.41"
    assert reality.pricing_flag.enabled is True
    assert reality.pricing_capacity.replicas == 4
