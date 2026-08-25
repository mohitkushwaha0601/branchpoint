"""Lightweight run events for the eventual live timeline."""

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from app.domain.primitives import DomainModel, ScalarValue, utc_now


class RunEventType(StrEnum):
    """Every observable step of a run."""

    RUN_CREATED = "RUN_CREATED"
    OBSERVATION_COMPLETED = "OBSERVATION_COMPLETED"
    TRUEFORGE_SESSION_CREATED = "TRUEFORGE_SESSION_CREATED"
    PLANNER_STARTED = "PLANNER_STARTED"
    PLANNER_COMPLETED = "PLANNER_COMPLETED"
    CANDIDATES_PLANNED = "CANDIDATES_PLANNED"
    WORLD_CREATED = "WORLD_CREATED"
    WORLD_EXECUTION_STARTED = "WORLD_EXECUTION_STARTED"
    WORLD_EXECUTION_COMPLETED = "WORLD_EXECUTION_COMPLETED"
    WORLD_AGENT_STARTED = "WORLD_AGENT_STARTED"
    DOPPELGANGER_STARTED = "DOPPELGANGER_STARTED"
    DOPPELGANGER_SPAWNED = "DOPPELGANGER_SPAWNED"
    DOPPELGANGER_RUNNING = "DOPPELGANGER_RUNNING"
    SANDBOX_TEST_STARTED = "SANDBOX_TEST_STARTED"
    SANDBOX_TEST_COMPLETED = "SANDBOX_TEST_COMPLETED"
    COUNTEREXAMPLE_PROPOSED = "COUNTEREXAMPLE_PROPOSED"
    COUNTEREXAMPLE_REPRODUCED = "COUNTEREXAMPLE_REPRODUCED"
    COUNTEREXAMPLE_REJECTED = "COUNTEREXAMPLE_REJECTED"
    WORLD_VETOED = "WORLD_VETOED"
    WORLD_SURVIVED = "WORLD_SURVIVED"
    COMPARISON_COMPLETED = "COMPARISON_COMPLETED"
    APPROVAL_REQUESTED = "APPROVAL_REQUESTED"
    APPROVAL_GRANTED = "APPROVAL_GRANTED"
    APPROVAL_REJECTED = "APPROVAL_REJECTED"
    COMMIT_STARTED = "COMMIT_STARTED"
    COMMIT_COMPLETED = "COMMIT_COMPLETED"
    VERIFICATION_STARTED = "VERIFICATION_STARTED"
    VERIFICATION_COMPLETED = "VERIFICATION_COMPLETED"
    RUN_SUCCEEDED = "RUN_SUCCEEDED"
    RUN_REJECTED = "RUN_REJECTED"
    RUN_FAILED = "RUN_FAILED"


class RunEvent(DomainModel):
    """One timeline entry for a run.

    Events carry *actions, tool usage, status, evidence, and outcomes* — never
    model reasoning. TrueForge exposes ``reasoning_content`` on its own
    ``model.message`` events; BRANCHPOINT deliberately never copies that into
    ``summary`` or ``payload``, so private chain-of-thought cannot leak into a
    stream that will eventually be rendered to users.
    """

    event_id: str
    run_id: str
    event_type: RunEventType
    summary: str
    occurred_at: datetime = Field(default_factory=utc_now)
    world_id: str | None = None
    payload: dict[str, ScalarValue] = Field(default_factory=dict)
