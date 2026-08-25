"""Human approval: the gate between a surviving counterfactual and reality."""

from datetime import datetime
from enum import StrEnum

from app.domain.errors import InvariantViolationError
from app.domain.primitives import DomainModel, evolve, utc_now


class ApprovalStatus(StrEnum):
    """Decision state of an approval request."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class Approval(DomainModel):
    """An approval bound to one exact world and one exact candidate action.

    ``action_fingerprint`` binds the decision to the content of the action that
    was reviewed. If the action changes after approval, the fingerprint no
    longer matches and the approval cannot be used to commit.
    """

    approval_id: str
    run_id: str
    selected_world_id: str
    action_id: str
    action_fingerprint: str
    requested_at: datetime
    status: ApprovalStatus = ApprovalStatus.PENDING
    decided_at: datetime | None = None
    actor: str | None = None
    reason: str = ""

    @property
    def is_granted(self) -> bool:
        """Whether a human explicitly approved this exact world and action."""
        return self.status is ApprovalStatus.APPROVED

    def decide(
        self,
        *,
        approved: bool,
        actor: str,
        reason: str = "",
        at: datetime | None = None,
    ) -> "Approval":
        """Record a human decision on a pending approval."""
        if self.status is not ApprovalStatus.PENDING:
            raise InvariantViolationError(
                "approval decided once",
                f"approval {self.approval_id} is already {self.status}",
            )
        return evolve(
            self,
            status=ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED,
            actor=actor,
            reason=reason,
            decided_at=at or utc_now(),
        )
