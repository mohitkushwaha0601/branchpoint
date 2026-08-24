"""Run state machine: legal and forbidden transitions."""

import pytest

from app.domain.errors import IllegalTransitionError
from app.domain.runs.lifecycle import (
    ALLOWED_RUN_TRANSITIONS,
    TERMINAL_RUN_STATUSES,
    RunStatus,
    can_transition,
)
from app.domain.runs.models import BranchpointRun
from tests.factories import FIXED_TIME, make_incident

HAPPY_PATH = (
    RunStatus.CREATED,
    RunStatus.OBSERVING,
    RunStatus.PLANNING,
    RunStatus.FORKING,
    RunStatus.EXECUTING_WORLDS,
    RunStatus.ADVERSARIAL_TESTING,
    RunStatus.COMPARING,
    RunStatus.AWAITING_APPROVAL,
    RunStatus.APPROVED,
    RunStatus.COMMITTING,
    RunStatus.VERIFYING,
    RunStatus.SUCCEEDED,
)

FORBIDDEN_TRANSITIONS = (
    (RunStatus.CREATED, RunStatus.COMMITTING),
    (RunStatus.AWAITING_APPROVAL, RunStatus.SUCCEEDED),
    (RunStatus.REJECTED, RunStatus.COMMITTING),
    (RunStatus.CREATED, RunStatus.APPROVED),
    (RunStatus.COMPARING, RunStatus.COMMITTING),
    (RunStatus.PLANNING, RunStatus.AWAITING_APPROVAL),
    (RunStatus.SUCCEEDED, RunStatus.VERIFYING),
    (RunStatus.FAILED, RunStatus.OBSERVING),
    (RunStatus.APPROVED, RunStatus.VERIFYING),
)


def new_run() -> BranchpointRun:
    """Return a freshly created run."""
    return BranchpointRun.create(run_id="run_1", incident=make_incident(), at=FIXED_TIME)


def test_new_run_starts_in_created() -> None:
    run = new_run()

    assert run.status is RunStatus.CREATED
    assert not run.is_terminal
    assert run.worlds == ()
    assert run.approval is None


def test_full_happy_path_transitions_are_legal() -> None:
    run = new_run()

    for status in HAPPY_PATH[1:]:
        run = run.transition_to(status, at=FIXED_TIME)

    assert run.status is RunStatus.SUCCEEDED
    assert run.is_terminal


@pytest.mark.parametrize(("current", "requested"), FORBIDDEN_TRANSITIONS)
def test_forbidden_transitions_are_rejected(current: RunStatus, requested: RunStatus) -> None:
    run = new_run()
    run = run.model_copy(update={"status": current})

    assert not can_transition(current, requested)
    with pytest.raises(IllegalTransitionError):
        run.transition_to(requested, at=FIXED_TIME)


@pytest.mark.parametrize("status", sorted(TERMINAL_RUN_STATUSES))
def test_terminal_statuses_allow_no_further_transition(status: RunStatus) -> None:
    assert ALLOWED_RUN_TRANSITIONS[status] == frozenset()


@pytest.mark.parametrize(
    "status", [status for status in RunStatus if status not in TERMINAL_RUN_STATUSES]
)
def test_every_non_terminal_status_can_fail(status: RunStatus) -> None:
    assert can_transition(status, RunStatus.FAILED)


def test_failing_a_run_records_a_reason() -> None:
    run = new_run().transition_to(RunStatus.OBSERVING, at=FIXED_TIME)

    failed = run.fail("observation timed out", at=FIXED_TIME)

    assert failed.status is RunStatus.FAILED
    assert failed.failure_reason == "observation timed out"


def test_a_terminal_run_cannot_be_failed_again() -> None:
    run = new_run().model_copy(update={"status": RunStatus.SUCCEEDED})

    with pytest.raises(IllegalTransitionError):
        run.fail("too late", at=FIXED_TIME)


def test_transitions_do_not_mutate_the_original_run() -> None:
    run = new_run()

    moved = run.transition_to(RunStatus.OBSERVING, at=FIXED_TIME)

    assert run.status is RunStatus.CREATED
    assert moved is not run
