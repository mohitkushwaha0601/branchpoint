"""Deterministic world comparison."""

from app.application.world_engine.comparator import compare_worlds
from app.domain.comparison.models import RejectionReason
from app.domain.evidence.models import EvidenceKind, EvidenceSeverity
from app.domain.worlds.lifecycle import WorldStatus
from app.domain.worlds.models import CounterexampleStatus, World, WorldVerdict
from tests.factories import (
    FIXED_TIME,
    completed_world,
    make_action,
    make_counterexample,
    make_evidence,
    make_outcome,
)


def vetoed(world_id: str = "world_vetoed") -> World:
    """A world vetoed by a reproduced, machine-verifiable counterexample."""
    return completed_world(
        world_id=world_id,
        action=make_action(f"{world_id}_action"),
        attack_evidence=(
            make_evidence(
                f"{world_id}_attack",
                kind=EvidenceKind.TEST_RESULT,
                passed=False,
                machine_verifiable=True,
            ),
        ),
        counterexamples=(
            make_counterexample(
                f"{world_id}_cx",
                world_id,
                status=CounterexampleStatus.REPRODUCED,
                evidence_ids=(f"{world_id}_attack",),
            ),
        ),
    )


def failed(world_id: str = "world_failed") -> World:
    """A world whose counterfactual execution failed."""
    return completed_world(
        world_id=world_id,
        action=make_action(f"{world_id}_action"),
        outcome=make_outcome(succeeded=False),
    )


def survivor(world_id: str, **outcome_overrides: object) -> World:
    """A surviving world with the given measured outcome."""
    return completed_world(
        world_id=world_id,
        action=make_action(f"{world_id}_action"),
        outcome=make_outcome(**outcome_overrides),  # type: ignore[arg-type]
    )


def executor_crashed_world(world_id: str = "world_crashed") -> World:
    """A world settled EXECUTION_FAILED with no outcome, matching what the
    orchestrator produces when the executor port raises before any execution
    result is recorded (see ``BranchpointOrchestrator.execute_worlds``)."""
    world = World.create(
        world_id=world_id,
        run_id="run_1",
        candidate_action=make_action(f"{world_id}_action"),
        at=FIXED_TIME,
    )
    world = world.transition_to(WorldStatus.PREPARING, at=FIXED_TIME)
    world = world.transition_to(WorldStatus.EXECUTING, at=FIXED_TIME)
    return world.settle(WorldVerdict.EXECUTION_FAILED, "executor error: boom", at=FIXED_TIME)


def test_vetoed_world_is_rejected_with_its_reason() -> None:
    result = compare_worlds([vetoed(), survivor("world_ok")])

    assert result.recommended_world_id == "world_ok"
    assert result.eligible_world_ids == ("world_ok",)
    rejected = {item.world_id: item for item in result.rejected_worlds}
    assert RejectionReason.ADVERSARIAL_VETO in rejected["world_vetoed"].reasons
    assert rejected["world_vetoed"].evidence_ids == ("world_vetoed_attack",)


def test_failed_world_is_rejected() -> None:
    result = compare_worlds([failed(), survivor("world_ok")])

    rejected = {item.world_id: item for item in result.rejected_worlds}
    assert RejectionReason.EXECUTION_FAILED in rejected["world_failed"].reasons
    assert result.recommended_world_id == "world_ok"


def test_executor_crash_with_no_outcome_is_rejected_as_execution_failed() -> None:
    """A crashed executor must not be misreported as NOT_EVALUATED: the world
    does have a verdict, it just never produced an execution outcome."""
    crashed = executor_crashed_world()

    result = compare_worlds([crashed, survivor("world_ok")])

    rejected = {item.world_id: item for item in result.rejected_worlds}
    assert rejected["world_crashed"].reasons == (RejectionReason.EXECUTION_FAILED,)
    assert "boom" in rejected["world_crashed"].detail
    assert result.recommended_world_id == "world_ok"


def test_no_recommendation_when_every_world_is_disqualified() -> None:
    result = compare_worlds([vetoed("world_a"), failed("world_b")])

    assert result.recommended_world_id is None
    assert not result.has_recommendation
    assert result.eligible_world_ids == ()
    assert len(result.rejected_worlds) == 2
    assert "No world survived" in result.summary


def test_empty_comparison_recommends_nothing() -> None:
    result = compare_worlds([])

    assert result.recommended_world_id is None
    assert result.rejected_worlds == ()


def test_deterministic_tie_is_represented_not_broken() -> None:
    result = compare_worlds([survivor("world_a"), survivor("world_b")])

    assert result.recommended_world_id is None
    assert result.is_tied
    assert result.tied_world_ids == ("world_a", "world_b")
    assert set(result.eligible_world_ids) == {"world_a", "world_b"}
    assert "tied" in result.summary


def test_goal_achievement_outranks_every_other_dimension() -> None:
    partial = survivor("world_partial", goal_achieved=False, goal_attainment=0.9, blast_radius=0)
    complete = survivor("world_complete", goal_achieved=True, goal_attainment=1.0, blast_radius=9)

    result = compare_worlds([partial, complete])

    assert result.recommended_world_id == "world_complete"
    ranks = {ranking.world_id: ranking.rank for ranking in result.rankings}
    assert ranks["world_complete"] < ranks["world_partial"]


def test_blast_radius_breaks_otherwise_equal_worlds() -> None:
    wide = survivor("world_wide", blast_radius=7)
    narrow = survivor("world_narrow", blast_radius=1)

    result = compare_worlds([wide, narrow])

    assert result.recommended_world_id == "world_narrow"


def test_cost_impact_is_the_final_deterministic_dimension() -> None:
    cheap = survivor("world_cheap", cost_delta=0.0)
    costly = survivor("world_costly", cost_delta=0.4)

    result = compare_worlds([cheap, costly])

    assert result.recommended_world_id == "world_cheap"
    assert result.rankings[0].world_id == "world_cheap"
    assert result.rankings[1].rank == 2


def test_critical_data_integrity_failure_disqualifies() -> None:
    world = completed_world(
        world_id="world_data",
        execution_evidence=(
            make_evidence(
                "data_1",
                kind=EvidenceKind.DATA_INTEGRITY,
                passed=False,
                machine_verifiable=True,
                severity=EvidenceSeverity.CRITICAL,
                claim="no orphaned order rows",
            ),
        ),
    )

    result = compare_worlds([world])

    reasons = result.rejected_worlds[0].reasons
    assert RejectionReason.CRITICAL_DATA_INTEGRITY_FAILURE in reasons
    assert result.recommended_world_id is None


def test_unevaluated_world_cannot_be_recommended() -> None:
    unevaluated = World.create(
        world_id="world_new", run_id="run_1", candidate_action=make_action(), at=FIXED_TIME
    )

    result = compare_worlds([unevaluated])

    assert result.rejected_worlds[0].reasons == (RejectionReason.NOT_EVALUATED,)


def test_comparison_is_stable_regardless_of_input_order() -> None:
    a = survivor("world_a", blast_radius=1)
    b = survivor("world_b", blast_radius=4)
    c = vetoed("world_c")

    forward = compare_worlds([a, b, c])
    backward = compare_worlds([c, b, a])

    assert forward.recommended_world_id == backward.recommended_world_id == "world_a"
    assert forward.eligible_world_ids == backward.eligible_world_ids
