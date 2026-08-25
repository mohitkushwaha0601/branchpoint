"""Deterministic world state machine."""

from collections.abc import Mapping
from enum import StrEnum

from app.domain.errors import IllegalTransitionError


class WorldStatus(StrEnum):
    """Lifecycle position of a counterfactual world."""

    CREATED = "CREATED"
    PREPARING = "PREPARING"
    EXECUTING = "EXECUTING"
    ATTACKING = "ATTACKING"
    EVALUATING = "EVALUATING"
    SURVIVED = "SURVIVED"
    VETOED = "VETOED"
    FAILED = "FAILED"


TERMINAL_WORLD_STATUSES: frozenset[WorldStatus] = frozenset(
    {WorldStatus.SURVIVED, WorldStatus.VETOED, WorldStatus.FAILED}
)

ALLOWED_WORLD_TRANSITIONS: Mapping[WorldStatus, frozenset[WorldStatus]] = {
    WorldStatus.CREATED: frozenset({WorldStatus.PREPARING, WorldStatus.FAILED}),
    WorldStatus.PREPARING: frozenset({WorldStatus.EXECUTING, WorldStatus.FAILED}),
    WorldStatus.EXECUTING: frozenset({WorldStatus.ATTACKING, WorldStatus.FAILED}),
    WorldStatus.ATTACKING: frozenset({WorldStatus.EVALUATING, WorldStatus.FAILED}),
    WorldStatus.EVALUATING: frozenset(
        {WorldStatus.SURVIVED, WorldStatus.VETOED, WorldStatus.FAILED}
    ),
    WorldStatus.SURVIVED: frozenset(),
    WorldStatus.VETOED: frozenset(),
    WorldStatus.FAILED: frozenset(),
}


def can_transition(current: WorldStatus, requested: WorldStatus) -> bool:
    """Whether a world may move from ``current`` to ``requested``."""
    return requested in ALLOWED_WORLD_TRANSITIONS[current]


def assert_world_transition(current: WorldStatus, requested: WorldStatus) -> None:
    """Raise :class:`IllegalTransitionError` if the transition is not permitted."""
    if not can_transition(current, requested):
        raise IllegalTransitionError("World", current, requested)
