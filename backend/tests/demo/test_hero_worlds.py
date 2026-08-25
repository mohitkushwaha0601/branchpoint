"""Alpha (rollback), beta (flag disable), and gamma (scale) world behavior.

Each world is driven through the real Phase 1 domain (World.create ->
transitions -> record_execution/record_attacks -> settle) using the real
Phase 2 demo adapters, exactly as the orchestrator would drive it. Nothing
here hardcodes a verdict by action name.
"""

from app.domain.actions.models import ActionType, RiskClass
from app.domain.primitives import utc_now
from app.domain.worlds.lifecycle import WorldStatus
from app.domain.worlds.models import World, WorldVerdict
from app.domain.worlds.verdicts import derive_verdict
from app.infrastructure.demo.adapters import DemoWorldExecutor
from app.infrastructure.demo.engine import DemoProductionEngine
from app.infrastructure.demo.hero import HeroAdversarialTester
from tests.factories import make_action

ALPHA_ACTION = make_action(
    "action_alpha",
    name="Roll back pricing-service to v2.40",
    action_type=ActionType.ROLLBACK,
    parameters={"version": "v2.40"},
    risk_class=RiskClass.HIGH,
)
BETA_ACTION = make_action(
    "action_beta",
    name="Disable PRICING_V2 feature flag",
    action_type=ActionType.FEATURE_FLAG_DISABLE,
    parameters={"flag_key": "PRICING_V2"},
    risk_class=RiskClass.LOW,
)
GAMMA_ACTION = make_action(
    "action_gamma",
    name="Scale pricing-service to 12 replicas",
    action_type=ActionType.SCALE,
    parameters={"target_replicas": 12},
    risk_class=RiskClass.MEDIUM,
)


async def _execute_and_attack(engine: DemoProductionEngine, world_id: str, action) -> World:
    """Drive one world through PREPARING -> EXECUTING -> ATTACKING -> EVALUATING -> settled,
    using the real DemoWorldExecutor and HeroAdversarialTester."""
    executor = DemoWorldExecutor(engine)
    attacker = HeroAdversarialTester(engine)

    world = World.create(world_id=world_id, run_id="run_1", candidate_action=action, at=utc_now())
    world = world.transition_to(WorldStatus.PREPARING).transition_to(WorldStatus.EXECUTING)
    report = await executor.execute(world)
    world = world.record_execution(report)

    world = world.transition_to(WorldStatus.ATTACKING)
    attack_report = await attacker.attack(world)
    world = world.record_attacks(attack_report)

    world = world.transition_to(WorldStatus.EVALUATING)
    verdict, reason = derive_verdict(world)
    return world.settle(verdict, reason)


# ----- alpha: rollback ------------------------------------------------------


async def test_alpha_execution_restores_headline_error_metrics() -> None:
    engine = DemoProductionEngine()
    executor = DemoWorldExecutor(engine)
    world = World.create(
        world_id="world_alpha", run_id="run_1", candidate_action=ALPHA_ACTION, at=utc_now()
    )
    world = world.transition_to(WorldStatus.PREPARING).transition_to(WorldStatus.EXECUTING)

    report = await executor.execute(world)

    assert report.outcome.goal_achieved is True
    assert report.outcome.regressions_detected == 0
    assert all(item.passed for item in report.evidence)


async def test_alpha_rollback_compatibility_check_fails() -> None:
    from app.infrastructure.demo.workload import order_deserialization_or_compatibility

    engine = DemoProductionEngine()
    await engine.snapshot_world("world_alpha")
    after = await engine.apply_to_world("world_alpha", ALPHA_ACTION)

    result = order_deserialization_or_compatibility(after)

    assert result.passed is False


async def test_alpha_compatibility_failure_is_machine_verifiable() -> None:
    engine = DemoProductionEngine()
    world = await _execute_and_attack(engine, "world_alpha", ALPHA_ACTION)

    failing = [item for item in world.evidence if not item.passed]
    assert failing
    assert all(item.machine_verifiable for item in failing)


async def test_alpha_compatibility_failure_references_the_v241_order() -> None:
    engine = DemoProductionEngine()
    world = await _execute_and_attack(engine, "world_alpha", ALPHA_ACTION)

    failing = [item for item in world.evidence if not item.passed]
    assert any(item.artifact and item.artifact.startswith("order:") for item in failing)


async def test_alpha_evidence_produces_a_valid_adversarial_veto() -> None:
    engine = DemoProductionEngine()
    world = await _execute_and_attack(engine, "world_alpha", ALPHA_ACTION)

    assert world.verdict is WorldVerdict.VETOED
    assert world.status is WorldStatus.VETOED
    reproduced = [cx for cx in world.counterexamples if cx.status.value == "REPRODUCED"]
    assert reproduced


# ----- beta: disable PRICING_V2 ---------------------------------------------


async def test_beta_restores_recovery_slo() -> None:
    from app.infrastructure.demo.metrics import (
        RECOVERY_SLO_ERROR_RATE_THRESHOLD,
        RECOVERY_SLO_P95_MS_THRESHOLD,
        compute_metrics,
    )

    engine = DemoProductionEngine()
    await engine.snapshot_world("world_beta")
    after = await engine.apply_to_world("world_beta", BETA_ACTION)
    metrics = compute_metrics(after)

    assert metrics.checkout_error_rate <= RECOVERY_SLO_ERROR_RATE_THRESHOLD
    assert metrics.checkout_p95_ms <= RECOVERY_SLO_P95_MS_THRESHOLD


async def test_beta_regression_suite_all_pass() -> None:
    engine = DemoProductionEngine()
    world = await _execute_and_attack(engine, "world_beta", BETA_ACTION)

    assert all(item.passed for item in world.evidence)


async def test_beta_data_integrity_passes() -> None:
    from app.infrastructure.demo.workload import data_integrity

    engine = DemoProductionEngine()
    await engine.snapshot_world("world_beta")
    after = await engine.apply_to_world("world_beta", BETA_ACTION)

    assert data_integrity(after).passed is True


async def test_beta_cost_does_not_materially_increase() -> None:
    engine = DemoProductionEngine()
    executor = DemoWorldExecutor(engine)
    world = World.create(
        world_id="world_beta", run_id="run_1", candidate_action=BETA_ACTION, at=utc_now()
    )
    world = world.transition_to(WorldStatus.PREPARING).transition_to(WorldStatus.EXECUTING)

    report = await executor.execute(world)

    assert report.outcome.cost_delta == 0.0


async def test_beta_survives() -> None:
    engine = DemoProductionEngine()
    world = await _execute_and_attack(engine, "world_beta", BETA_ACTION)

    assert world.verdict is WorldVerdict.SURVIVED
    assert world.status is WorldStatus.SURVIVED


# ----- gamma: scale ----------------------------------------------------------


async def test_gamma_improves_metrics_relative_to_reality() -> None:
    from app.infrastructure.demo.metrics import compute_metrics

    engine = DemoProductionEngine()
    reality = await engine.reality()
    reality_metrics = compute_metrics(reality)

    await engine.snapshot_world("world_gamma")
    after = await engine.apply_to_world("world_gamma", GAMMA_ACTION)
    after_metrics = compute_metrics(after)

    assert after_metrics.checkout_error_rate < reality_metrics.checkout_error_rate
    assert after_metrics.checkout_p95_ms < reality_metrics.checkout_p95_ms


async def test_gamma_does_not_fully_remove_the_root_cause() -> None:
    from app.infrastructure.demo.metrics import RECOVERY_SLO_ERROR_RATE_THRESHOLD, compute_metrics

    engine = DemoProductionEngine()
    await engine.snapshot_world("world_gamma")
    after = await engine.apply_to_world("world_gamma", GAMMA_ACTION)
    metrics = compute_metrics(after)

    assert metrics.regression_active is True
    assert metrics.checkout_error_rate > RECOVERY_SLO_ERROR_RATE_THRESHOLD


async def test_gamma_cost_increases_deterministically() -> None:
    engine = DemoProductionEngine()
    executor = DemoWorldExecutor(engine)
    world = World.create(
        world_id="world_gamma", run_id="run_1", candidate_action=GAMMA_ACTION, at=utc_now()
    )
    world = world.transition_to(WorldStatus.PREPARING).transition_to(WorldStatus.EXECUTING)

    report = await executor.execute(world)

    assert report.outcome.cost_delta == 900.0


async def test_gamma_does_not_achieve_the_goal_but_is_not_vetoed() -> None:
    engine = DemoProductionEngine()
    world = await _execute_and_attack(engine, "world_gamma", GAMMA_ACTION)

    assert world.outcome is not None
    assert world.outcome.goal_achieved is False
    assert world.verdict is WorldVerdict.SURVIVED
