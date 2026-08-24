"""The BranchpointRun aggregate: one complete decision process."""

from datetime import datetime

from app.domain.actions.models import CandidateAction
from app.domain.approvals.models import Approval
from app.domain.commits.models import CommitReceipt
from app.domain.comparison.models import ComparisonResult
from app.domain.errors import InvariantViolationError
from app.domain.incidents.models import Incident, ObservedState
from app.domain.primitives import DomainModel, evolve, utc_now
from app.domain.runs.lifecycle import TERMINAL_RUN_STATUSES, RunStatus, assert_run_transition
from app.domain.verification.models import VerificationResult
from app.domain.worlds.models import World, WorldVerdict


class BranchpointRun(DomainModel):
    """One incident, many counterfactual worlds, at most one committed action."""

    run_id: str
    incident: Incident
    created_at: datetime
    updated_at: datetime
    status: RunStatus = RunStatus.CREATED
    observed_state: ObservedState | None = None
    candidate_actions: tuple[CandidateAction, ...] = ()
    worlds: tuple[World, ...] = ()
    comparison: ComparisonResult | None = None
    selected_world_id: str | None = None
    approval: Approval | None = None
    commit_receipt: CommitReceipt | None = None
    verification: VerificationResult | None = None
    failure_reason: str = ""

    @classmethod
    def create(
        cls, *, run_id: str, incident: Incident, at: datetime | None = None
    ) -> "BranchpointRun":
        """Open a new run in ``CREATED`` state."""
        now = at or utc_now()
        return cls(run_id=run_id, incident=incident, created_at=now, updated_at=now)

    @property
    def is_terminal(self) -> bool:
        """Whether the run has reached a terminal status."""
        return self.status in TERMINAL_RUN_STATUSES

    @property
    def surviving_worlds(self) -> tuple[World, ...]:
        """Worlds whose evidence-backed verdict is ``SURVIVED``."""
        return tuple(world for world in self.worlds if world.verdict is WorldVerdict.SURVIVED)

    def world(self, world_id: str) -> World | None:
        """Return the world with ``world_id``, or ``None``."""
        return next((world for world in self.worlds if world.world_id == world_id), None)

    def require_world(self, world_id: str) -> World:
        """Return the world with ``world_id`` or raise if this run does not own it."""
        world = self.world(world_id)
        if world is None:
            raise InvariantViolationError(
                "world belongs to run", f"run {self.run_id} has no world {world_id}"
            )
        return world

    def transition_to(self, status: RunStatus, *, at: datetime | None = None) -> "BranchpointRun":
        """Return a copy of this run moved to ``status``, enforcing the state machine."""
        assert_run_transition(self.status, status)
        return evolve(self, status=status, updated_at=at or utc_now())

    def with_observation(
        self, observed_state: ObservedState, *, at: datetime | None = None
    ) -> "BranchpointRun":
        """Attach structured observations of reality."""
        return evolve(self, observed_state=observed_state, updated_at=at or utc_now())

    def with_candidates(
        self, candidate_actions: tuple[CandidateAction, ...], *, at: datetime | None = None
    ) -> "BranchpointRun":
        """Attach the proposed candidate actions."""
        return evolve(self, candidate_actions=candidate_actions, updated_at=at or utc_now())

    def with_worlds(
        self, worlds: tuple[World, ...], *, at: datetime | None = None
    ) -> "BranchpointRun":
        """Attach the forked worlds."""
        return evolve(self, worlds=worlds, updated_at=at or utc_now())

    def replace_world(self, world: World, *, at: datetime | None = None) -> "BranchpointRun":
        """Replace one world in place, preserving world order."""
        self.require_world(world.world_id)
        replaced = tuple(
            world if existing.world_id == world.world_id else existing for existing in self.worlds
        )
        return evolve(self, worlds=replaced, updated_at=at or utc_now())

    def with_comparison(
        self, comparison: ComparisonResult, *, at: datetime | None = None
    ) -> "BranchpointRun":
        """Attach the deterministic comparison result."""
        return evolve(self, comparison=comparison, updated_at=at or utc_now())

    def with_approval(self, approval: Approval, *, at: datetime | None = None) -> "BranchpointRun":
        """Attach an approval and record which world it selects."""
        return evolve(
            self,
            approval=approval,
            selected_world_id=approval.selected_world_id,
            updated_at=at or utc_now(),
        )

    def with_commit_receipt(
        self, commit_receipt: CommitReceipt, *, at: datetime | None = None
    ) -> "BranchpointRun":
        """Attach the receipt describing what was done to reality."""
        return evolve(self, commit_receipt=commit_receipt, updated_at=at or utc_now())

    def with_verification(
        self, verification: VerificationResult, *, at: datetime | None = None
    ) -> "BranchpointRun":
        """Attach the independent post-commit verification result."""
        return evolve(self, verification=verification, updated_at=at or utc_now())

    def fail(self, reason: str, *, at: datetime | None = None) -> "BranchpointRun":
        """Move the run to ``FAILED`` with an explicit reason."""
        assert_run_transition(self.status, RunStatus.FAILED)
        return evolve(
            self,
            status=RunStatus.FAILED,
            failure_reason=reason,
            updated_at=at or utc_now(),
        )
