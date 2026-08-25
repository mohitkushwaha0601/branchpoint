"""World state machine and evidence recording guards."""

import pytest

from app.domain.errors import IllegalTransitionError, InvariantViolationError
from app.domain.worlds.lifecycle import (
    ALLOWED_WORLD_TRANSITIONS,
    TERMINAL_WORLD_STATUSES,
    WorldStatus,
    can_transition,
)
from app.domain.worlds.models import AdversarialReport, World, WorldExecutionReport, WorldVerdict
from tests.factories import FIXED_TIME, make_action, make_evidence, make_outcome

FORBIDDEN_TRANSITIONS = (
    (WorldStatus.CREATED, WorldStatus.EXECUTING),
    (WorldStatus.CREATED, WorldStatus.SURVIVED),
    (WorldStatus.PREPARING, WorldStatus.ATTACKING),
    (WorldStatus.EXECUTING, WorldStatus.SURVIVED),
    (WorldStatus.ATTACKING, WorldStatus.VETOED),
    (WorldStatus.SURVIVED, WorldStatus.EVALUATING),
    (WorldStatus.VETOED, WorldStatus.SURVIVED),
)


def new_world() -> World:
    """Return a freshly forked world."""
    return World.create(
        world_id="world_1", run_id="run_1", candidate_action=make_action(), at=FIXED_TIME
    )


def test_world_starts_in_created_without_a_verdict() -> None:
    world = new_world()

    assert world.status is WorldStatus.CREATED
    assert world.verdict is None
    assert not world.is_terminal


def test_legal_world_path_reaches_a_verdict() -> None:
    world = new_world()

    for status in (
        WorldStatus.PREPARING,
        WorldStatus.EXECUTING,
        WorldStatus.ATTACKING,
        WorldStatus.EVALUATING,
    ):
        world = world.transition_to(status, at=FIXED_TIME)
    settled = world.settle(WorldVerdict.SURVIVED, "no failing evidence", at=FIXED_TIME)

    assert settled.status is WorldStatus.SURVIVED
    assert settled.is_terminal
    assert settled.verdict_reason == "no failing evidence"


@pytest.mark.parametrize(("current", "requested"), FORBIDDEN_TRANSITIONS)
def test_forbidden_world_transitions_are_rejected(
    current: WorldStatus, requested: WorldStatus
) -> None:
    world = new_world().model_copy(update={"status": current})

    assert not can_transition(current, requested)
    with pytest.raises(IllegalTransitionError):
        world.transition_to(requested, at=FIXED_TIME)


@pytest.mark.parametrize("status", sorted(TERMINAL_WORLD_STATUSES))
def test_terminal_world_statuses_are_final(status: WorldStatus) -> None:
    assert ALLOWED_WORLD_TRANSITIONS[status] == frozenset()


def test_execution_can_only_be_recorded_while_executing() -> None:
    world = new_world()

    with pytest.raises(InvariantViolationError):
        world.record_execution(WorldExecutionReport(outcome=make_outcome()), at=FIXED_TIME)


def test_attacks_can_only_be_recorded_while_attacking() -> None:
    world = new_world().transition_to(WorldStatus.PREPARING, at=FIXED_TIME)

    with pytest.raises(InvariantViolationError):
        world.record_attacks(AdversarialReport(), at=FIXED_TIME)


def test_recording_execution_appends_evidence() -> None:
    world = new_world().transition_to(WorldStatus.PREPARING, at=FIXED_TIME)
    world = world.transition_to(WorldStatus.EXECUTING, at=FIXED_TIME)

    recorded = world.record_execution(
        WorldExecutionReport(outcome=make_outcome(), evidence=(make_evidence("e1"),)),
        at=FIXED_TIME,
    )

    assert recorded.outcome is not None
    assert [item.evidence_id for item in recorded.evidence] == ["e1"]
    assert world.evidence == ()


def test_inconclusive_verdict_lands_in_failed_status() -> None:
    world = new_world()
    for status in (
        WorldStatus.PREPARING,
        WorldStatus.EXECUTING,
        WorldStatus.ATTACKING,
        WorldStatus.EVALUATING,
    ):
        world = world.transition_to(status, at=FIXED_TIME)

    settled = world.settle(WorldVerdict.INCONCLUSIVE, "no evidence", at=FIXED_TIME)

    assert settled.status is WorldStatus.FAILED
    assert settled.verdict is WorldVerdict.INCONCLUSIVE
