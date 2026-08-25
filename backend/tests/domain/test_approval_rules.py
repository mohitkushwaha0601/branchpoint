"""The gate between a surviving counterfactual and reality."""

import pytest

from app.domain.approvals.models import ApprovalStatus
from app.domain.approvals.rules import assert_commit_allowed, build_approval_request
from app.domain.comparison.models import ComparisonResult, RejectedWorld, RejectionReason
from app.domain.errors import InvariantViolationError
from app.domain.evidence.models import EvidenceKind
from app.domain.runs.lifecycle import RunStatus
from app.domain.runs.models import BranchpointRun
from app.domain.worlds.models import CounterexampleStatus, World, WorldVerdict
from tests.factories import (
    FIXED_TIME,
    completed_world,
    make_action,
    make_counterexample,
    make_evidence,
    make_incident,
)


def surviving_world(world_id: str = "world_beta", action_id: str = "action_beta") -> World:
    """Return a world that survived on machine-verifiable evidence."""
    return completed_world(world_id=world_id, action=make_action(action_id))


def vetoed_world(world_id: str = "world_alpha", action_id: str = "action_alpha") -> World:
    """Return a world vetoed by a reproduced counterexample."""
    return completed_world(
        world_id=world_id,
        action=make_action(action_id, name="Roll back pricing-service"),
        attack_evidence=(
            make_evidence(
                "alpha_attack", kind=EvidenceKind.TEST_RESULT, passed=False, machine_verifiable=True
            ),
        ),
        counterexamples=(
            make_counterexample(
                "attack_1",
                world_id,
                status=CounterexampleStatus.REPRODUCED,
                evidence_ids=("alpha_attack",),
            ),
        ),
    )


def compared_run(
    *worlds: World, eligible: tuple[str, ...], recommended: str | None
) -> BranchpointRun:
    """Return a run parked in COMPARING with a comparison result."""
    run = BranchpointRun.create(run_id="run_1", incident=make_incident(), at=FIXED_TIME)
    run = run.model_copy(update={"status": RunStatus.COMPARING, "worlds": worlds})
    return run.with_comparison(
        ComparisonResult(
            recommended_world_id=recommended,
            eligible_world_ids=eligible,
            rejected_worlds=tuple(
                RejectedWorld(world_id=world.world_id, reasons=(RejectionReason.ADVERSARIAL_VETO,))
                for world in worlds
                if world.world_id not in eligible
            ),
            summary="test comparison",
        ),
        at=FIXED_TIME,
    )


def approved_run(run: BranchpointRun, world_id: str) -> BranchpointRun:
    """Drive a compared run through approval to the APPROVED state."""
    approval = build_approval_request(
        run, world_id, approval_id="approval_1", requested_at=FIXED_TIME
    )
    run = run.with_approval(approval, at=FIXED_TIME)
    run = run.transition_to(RunStatus.AWAITING_APPROVAL, at=FIXED_TIME)
    decided = run.approval.decide(approved=True, actor="sre@example.com", at=FIXED_TIME)
    run = run.with_approval(decided, at=FIXED_TIME)
    return run.transition_to(RunStatus.APPROVED, at=FIXED_TIME)


def test_approval_cannot_be_requested_before_comparison() -> None:
    run = BranchpointRun.create(run_id="run_1", incident=make_incident(), at=FIXED_TIME)
    run = run.model_copy(
        update={"status": RunStatus.ADVERSARIAL_TESTING, "worlds": (surviving_world(),)}
    )

    with pytest.raises(InvariantViolationError, match="approval follows comparison"):
        build_approval_request(run, "world_beta", approval_id="approval_1", requested_at=FIXED_TIME)


def test_approval_cannot_target_a_vetoed_world() -> None:
    veto = vetoed_world()
    run = compared_run(veto, eligible=(), recommended=None)

    with pytest.raises(InvariantViolationError, match="only surviving worlds"):
        build_approval_request(
            run, veto.world_id, approval_id="approval_1", requested_at=FIXED_TIME
        )


def test_approval_cannot_target_a_world_comparison_rejected() -> None:
    survived = surviving_world()
    run = compared_run(survived, eligible=(), recommended=None)

    with pytest.raises(InvariantViolationError, match="only eligible worlds"):
        build_approval_request(
            run, survived.world_id, approval_id="approval_1", requested_at=FIXED_TIME
        )


def test_only_one_approval_per_run() -> None:
    survived = surviving_world()
    run = compared_run(survived, eligible=(survived.world_id,), recommended=survived.world_id)
    approval = build_approval_request(
        run, survived.world_id, approval_id="approval_1", requested_at=FIXED_TIME
    )
    run = run.with_approval(approval, at=FIXED_TIME)

    with pytest.raises(InvariantViolationError, match="one approval per run"):
        build_approval_request(
            run, survived.world_id, approval_id="approval_2", requested_at=FIXED_TIME
        )


def test_approval_binds_the_exact_world_and_action() -> None:
    survived = surviving_world()
    run = compared_run(survived, eligible=(survived.world_id,), recommended=survived.world_id)

    approval = build_approval_request(
        run, survived.world_id, approval_id="approval_1", requested_at=FIXED_TIME
    )

    assert approval.status is ApprovalStatus.PENDING
    assert approval.selected_world_id == survived.world_id
    assert approval.action_id == survived.candidate_action.action_id
    assert approval.action_fingerprint == survived.candidate_action.fingerprint()


def test_an_approval_is_decided_only_once() -> None:
    survived = surviving_world()
    run = compared_run(survived, eligible=(survived.world_id,), recommended=survived.world_id)
    approval = build_approval_request(
        run, survived.world_id, approval_id="approval_1", requested_at=FIXED_TIME
    )

    decided = approval.decide(approved=True, actor="sre@example.com", at=FIXED_TIME)

    with pytest.raises(InvariantViolationError, match="approval decided once"):
        decided.decide(approved=False, actor="someone-else", at=FIXED_TIME)


def test_commit_is_blocked_without_an_approval() -> None:
    survived = surviving_world()
    run = compared_run(survived, eligible=(survived.world_id,), recommended=survived.world_id)

    with pytest.raises(InvariantViolationError, match="commit requires approval"):
        assert_commit_allowed(run)


def test_commit_is_blocked_while_approval_is_pending() -> None:
    survived = surviving_world()
    run = compared_run(survived, eligible=(survived.world_id,), recommended=survived.world_id)
    approval = build_approval_request(
        run, survived.world_id, approval_id="approval_1", requested_at=FIXED_TIME
    )
    run = run.with_approval(approval, at=FIXED_TIME)
    run = run.transition_to(RunStatus.AWAITING_APPROVAL, at=FIXED_TIME)

    with pytest.raises(InvariantViolationError, match="commit requires approval"):
        assert_commit_allowed(run)


def test_commit_is_allowed_for_a_correctly_bound_approval() -> None:
    survived = surviving_world()
    run = compared_run(survived, eligible=(survived.world_id,), recommended=survived.world_id)
    run = approved_run(run, survived.world_id)

    world = assert_commit_allowed(run)

    assert world.world_id == survived.world_id
    assert world.verdict is WorldVerdict.SURVIVED


def test_approval_is_not_transferable_when_the_action_changes() -> None:
    survived = surviving_world()
    run = compared_run(survived, eligible=(survived.world_id,), recommended=survived.world_id)
    run = approved_run(run, survived.world_id)

    tampered_action = survived.candidate_action.model_copy(
        update={"parameters": {"rollout_percentage": 100.0}}
    )
    tampered_world = survived.model_copy(update={"candidate_action": tampered_action})
    run = run.replace_world(tampered_world, at=FIXED_TIME)

    with pytest.raises(InvariantViolationError, match="approval is not transferable"):
        assert_commit_allowed(run)


def test_approval_is_not_transferable_to_a_different_action() -> None:
    survived = surviving_world()
    run = compared_run(survived, eligible=(survived.world_id,), recommended=survived.world_id)
    run = approved_run(run, survived.world_id)

    swapped = survived.model_copy(update={"candidate_action": make_action("action_other")})
    run = run.replace_world(swapped, at=FIXED_TIME)

    with pytest.raises(InvariantViolationError, match="approval binds the exact action"):
        assert_commit_allowed(run)


def test_fingerprint_changes_when_action_parameters_change() -> None:
    action = make_action("action_1", parameters={"flag": "pricing_v2"})
    changed = action.model_copy(update={"parameters": {"flag": "pricing_v3"}})

    assert action.fingerprint() != changed.fingerprint()
    assert (
        action.fingerprint()
        == make_action("action_1", parameters={"flag": "pricing_v2"}).fingerprint()
    )
