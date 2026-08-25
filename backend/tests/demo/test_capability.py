"""Commit capability: the one-time security boundary for mutating reality."""

import asyncio
import logging

import pytest

from app.domain.actions.models import ActionType
from app.domain.approvals.rules import build_approval_request
from app.domain.comparison.models import ComparisonResult
from app.domain.primitives import evolve
from app.domain.runs.lifecycle import RunStatus
from app.domain.runs.models import BranchpointRun
from app.domain.worlds.lifecycle import WorldStatus
from app.domain.worlds.models import World, WorldVerdict
from app.infrastructure.demo.capability import (
    CapabilityAlreadyUsedError,
    CapabilityExpiredError,
    CapabilityMismatchError,
    CapabilityNotFoundError,
    CapabilityStore,
)
from app.infrastructure.demo.engine import DemoProductionEngine
from tests.factories import FIXED_TIME, make_action, make_incident


def _survived_world(world_id: str, action) -> World:
    world = World.create(world_id=world_id, run_id="run_1", candidate_action=action, at=FIXED_TIME)
    return world.model_copy(
        update={"status": WorldStatus.SURVIVED, "verdict": WorldVerdict.SURVIVED}
    )


def approved_run(action) -> tuple[BranchpointRun, World]:
    """Build a run parked in APPROVED state for ``action``'s surviving world."""
    world = _survived_world("world_1", action)
    run = BranchpointRun.create(run_id="run_1", incident=make_incident(), at=FIXED_TIME)
    run = run.model_copy(update={"status": RunStatus.COMPARING, "worlds": (world,)})
    run = run.with_comparison(
        ComparisonResult(recommended_world_id="world_1", eligible_world_ids=("world_1",)),
        at=FIXED_TIME,
    )
    approval = build_approval_request(
        run, "world_1", approval_id="approval_1", requested_at=FIXED_TIME
    )
    run = run.with_approval(approval, at=FIXED_TIME).transition_to(
        RunStatus.AWAITING_APPROVAL, at=FIXED_TIME
    )
    decided = run.approval.decide(approved=True, actor="sre@example.com", at=FIXED_TIME)
    run = run.with_approval(decided, at=FIXED_TIME).transition_to(RunStatus.APPROVED, at=FIXED_TIME)
    return run, world


ACTION = make_action(
    "action_1", action_type=ActionType.FEATURE_FLAG_DISABLE, parameters={"flag_key": "PRICING_V2"}
)


async def test_mutation_without_capability_is_rejected() -> None:
    engine = DemoProductionEngine()
    run, world = approved_run(ACTION)
    store = CapabilityStore()

    with pytest.raises(CapabilityNotFoundError):
        await engine.apply_to_reality(
            run=run, world=world, capability_store=store, capability_token=None
        )  # type: ignore[arg-type]

    with pytest.raises(CapabilityNotFoundError):
        await engine.apply_to_reality(
            run=run, world=world, capability_store=store, capability_token=""
        )


async def test_invalid_capability_token_is_rejected() -> None:
    engine = DemoProductionEngine()
    run, world = approved_run(ACTION)
    store = CapabilityStore()

    with pytest.raises(CapabilityNotFoundError):
        await engine.apply_to_reality(
            run=run, world=world, capability_store=store, capability_token="cap_bad.wrongsecret"
        )


async def test_capability_for_a_different_action_is_rejected() -> None:
    engine = DemoProductionEngine()
    run, world = approved_run(ACTION)
    other_action = make_action(
        "action_other", action_type=ActionType.SCALE, parameters={"target_replicas": 12}
    )
    other_world = _survived_world("world_1", other_action)
    other_run = run.replace_world(other_world, at=FIXED_TIME)
    other_run = evolve(
        other_run,
        approval=evolve(
            run.approval,
            action_id="action_other",
            action_fingerprint=other_action.fingerprint(),
        ),
    )
    store = CapabilityStore()
    issued = await store.issue_for_approved_run(other_run)

    with pytest.raises(CapabilityMismatchError) as exc_info:
        await engine.apply_to_reality(
            run=run, world=world, capability_store=store, capability_token=issued.token
        )
    assert exc_info.value.field == "action"


async def test_capability_for_a_modified_action_is_rejected_via_fingerprint() -> None:
    engine = DemoProductionEngine()
    run, world = approved_run(ACTION)
    store = CapabilityStore()
    issued = await store.issue_for_approved_run(run)

    tampered_action = world.candidate_action.model_copy(
        update={"parameters": {"flag_key": "SOMETHING_ELSE"}}
    )
    tampered_world = world.model_copy(update={"candidate_action": tampered_action})

    with pytest.raises(CapabilityMismatchError) as exc_info:
        await engine.apply_to_reality(
            run=run, world=tampered_world, capability_store=store, capability_token=issued.token
        )
    assert exc_info.value.field == "action_fingerprint"


async def test_capability_for_a_different_world_is_rejected() -> None:
    engine = DemoProductionEngine()
    run, world = approved_run(ACTION)
    store = CapabilityStore()
    issued = await store.issue_for_approved_run(run)

    wrong_world = world.model_copy(update={"world_id": "world_wrong"})

    with pytest.raises(CapabilityMismatchError) as exc_info:
        await engine.apply_to_reality(
            run=run, world=wrong_world, capability_store=store, capability_token=issued.token
        )
    assert exc_info.value.field == "world"


async def test_valid_capability_succeeds() -> None:
    engine = DemoProductionEngine()
    run, world = approved_run(ACTION)
    store = CapabilityStore()
    issued = await store.issue_for_approved_run(run)

    receipts = await engine.apply_to_reality(
        run=run, world=world, capability_store=store, capability_token=issued.token
    )

    assert receipts[0].succeeded is True
    reality = await engine.reality()
    assert reality.pricing_flag.enabled is False


async def test_capability_replay_is_rejected() -> None:
    engine = DemoProductionEngine()
    run, world = approved_run(ACTION)
    store = CapabilityStore()
    issued = await store.issue_for_approved_run(run)

    await engine.apply_to_reality(
        run=run, world=world, capability_store=store, capability_token=issued.token
    )

    with pytest.raises(CapabilityAlreadyUsedError):
        await engine.apply_to_reality(
            run=run, world=world, capability_store=store, capability_token=issued.token
        )


async def test_expired_capability_is_rejected() -> None:
    engine = DemoProductionEngine()
    run, world = approved_run(ACTION)
    store = CapabilityStore(ttl_seconds=0.001)
    issued = await store.issue_for_approved_run(run)
    await asyncio.sleep(0.01)

    with pytest.raises(CapabilityExpiredError):
        await engine.apply_to_reality(
            run=run, world=world, capability_store=store, capability_token=issued.token
        )


async def test_capability_token_never_appears_in_logs(caplog: pytest.LogCaptureFixture) -> None:
    engine = DemoProductionEngine()
    run, world = approved_run(ACTION)
    store = CapabilityStore()

    with caplog.at_level(logging.DEBUG):
        issued = await store.issue_for_approved_run(run)
        await engine.apply_to_reality(
            run=run, world=world, capability_store=store, capability_token=issued.token
        )
        try:
            await engine.apply_to_reality(
                run=run, world=world, capability_store=store, capability_token=issued.token
            )
        except CapabilityAlreadyUsedError:
            pass

    secret = issued.token.split(".", 1)[1]
    for record in caplog.records:
        assert secret not in record.getMessage()
    assert secret not in repr(issued)
    assert secret not in repr(issued.capability)
