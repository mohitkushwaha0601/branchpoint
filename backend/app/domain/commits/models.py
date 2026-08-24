"""The immutable record of mutating reality."""

from datetime import datetime
from enum import StrEnum

from app.domain.primitives import DomainModel, evolve, utc_now


class CommitStatus(StrEnum):
    """Outcome of committing the approved action to reality."""

    STARTED = "STARTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class OperationReceipt(DomainModel):
    """The result of one individual mutation performed during a commit."""

    operation: str
    target: str
    succeeded: bool
    completed_at: datetime
    detail: str = ""
    reference: str | None = None


class CommitReceipt(DomainModel):
    """Immutable proof of what was actually done to reality.

    A commit receipt records the approved action's fingerprint, so the executed
    action can always be checked against the approved one after the fact.
    """

    commit_id: str
    run_id: str
    world_id: str
    action_id: str
    action_fingerprint: str
    started_at: datetime
    status: CommitStatus = CommitStatus.STARTED
    completed_at: datetime | None = None
    operations: tuple[OperationReceipt, ...] = ()
    evidence_ids: tuple[str, ...] = ()

    def complete(
        self,
        operations: tuple[OperationReceipt, ...],
        *,
        evidence_ids: tuple[str, ...] = (),
        at: datetime | None = None,
    ) -> "CommitReceipt":
        """Close the receipt; the commit succeeds only if every operation succeeded."""
        succeeded = bool(operations) and all(operation.succeeded for operation in operations)
        return evolve(
            self,
            operations=operations,
            evidence_ids=evidence_ids,
            status=CommitStatus.SUCCEEDED if succeeded else CommitStatus.FAILED,
            completed_at=at or utc_now(),
        )

    def fail(self, detail: str, *, at: datetime | None = None) -> "CommitReceipt":
        """Close the receipt as failed without any successful operation."""
        now = at or utc_now()
        return evolve(
            self,
            status=CommitStatus.FAILED,
            completed_at=now,
            operations=self.operations
            + (
                OperationReceipt(
                    operation="commit",
                    target=self.action_id,
                    succeeded=False,
                    detail=detail,
                    completed_at=now,
                ),
            ),
        )
