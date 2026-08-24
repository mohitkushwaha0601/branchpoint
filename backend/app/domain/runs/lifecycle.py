"""Deterministic BRANCHPOINT run state machine."""

from collections.abc import Mapping
from enum import StrEnum

from app.domain.errors import IllegalTransitionError


class RunStatus(StrEnum):
    """Lifecycle position of a run."""

    CREATED = "CREATED"
    OBSERVING = "OBSERVING"
    PLANNING = "PLANNING"
    FORKING = "FORKING"
    EXECUTING_WORLDS = "EXECUTING_WORLDS"
    ADVERSARIAL_TESTING = "ADVERSARIAL_TESTING"
    COMPARING = "COMPARING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    COMMITTING = "COMMITTING"
    VERIFYING = "VERIFYING"
    SUCCEEDED = "SUCCEEDED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


TERMINAL_RUN_STATUSES: frozenset[RunStatus] = frozenset(
    {RunStatus.SUCCEEDED, RunStatus.REJECTED, RunStatus.FAILED}
)

ALLOWED_RUN_TRANSITIONS: Mapping[RunStatus, frozenset[RunStatus]] = {
    RunStatus.CREATED: frozenset({RunStatus.OBSERVING, RunStatus.FAILED}),
    RunStatus.OBSERVING: frozenset({RunStatus.PLANNING, RunStatus.FAILED}),
    RunStatus.PLANNING: frozenset({RunStatus.FORKING, RunStatus.REJECTED, RunStatus.FAILED}),
    RunStatus.FORKING: frozenset({RunStatus.EXECUTING_WORLDS, RunStatus.FAILED}),
    RunStatus.EXECUTING_WORLDS: frozenset({RunStatus.ADVERSARIAL_TESTING, RunStatus.FAILED}),
    RunStatus.ADVERSARIAL_TESTING: frozenset({RunStatus.COMPARING, RunStatus.FAILED}),
    RunStatus.COMPARING: frozenset(
        {RunStatus.AWAITING_APPROVAL, RunStatus.REJECTED, RunStatus.FAILED}
    ),
    RunStatus.AWAITING_APPROVAL: frozenset(
        {RunStatus.APPROVED, RunStatus.REJECTED, RunStatus.FAILED}
    ),
    RunStatus.APPROVED: frozenset({RunStatus.COMMITTING, RunStatus.FAILED}),
    RunStatus.COMMITTING: frozenset({RunStatus.VERIFYING, RunStatus.FAILED}),
    RunStatus.VERIFYING: frozenset({RunStatus.SUCCEEDED, RunStatus.FAILED}),
    RunStatus.SUCCEEDED: frozenset(),
    RunStatus.REJECTED: frozenset(),
    RunStatus.FAILED: frozenset(),
}


def can_transition(current: RunStatus, requested: RunStatus) -> bool:
    """Whether a run may move from ``current`` to ``requested``."""
    return requested in ALLOWED_RUN_TRANSITIONS[current]


def assert_run_transition(current: RunStatus, requested: RunStatus) -> None:
    """Raise :class:`IllegalTransitionError` if the transition is not permitted."""
    if not can_transition(current, requested):
        raise IllegalTransitionError("BranchpointRun", current, requested)
