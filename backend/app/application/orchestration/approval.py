"""Human approval of the recommended world, and what it authorizes.

This is the coordinator behind ``POST /api/v1/runs/{run_id}/approval``. It is
deliberately thin: every safety decision already belongs to the deterministic
domain beneath it. What it adds is the *sequencing* of one human decision:

    AWAITING_APPROVAL
      → the human approves (no action content travels from the client)
      → the approval binds run/world/action/fingerprint
      → the sanctioned destructive tool path runs the commit
      → the one-time capability is spent inside that path
      → an independent verifier re-derives reality
      → SUCCEEDED only if verification PASSED

The client never says *what* to commit. It says "yes" to what BRANCHPOINT
already recommended, and may optionally restate the world/action/fingerprint it
believes it is approving — restating something different is a conflict, never an
override. That is the whole point: after approval, no model and no browser can
choose, modify, or substitute the action.
"""

from app.application.errors import ApplicationError, RunNotFoundError
from app.application.orchestration.orchestrator import BranchpointOrchestrator
from app.application.ports import (
    CommitOperator,
    CommitOperatorReport,
    EventSink,
    RunRepository,
)
from app.domain.approvals.models import ApprovalStatus
from app.domain.commits.models import CommitStatus
from app.domain.events import RunEvent, RunEventType
from app.domain.primitives import new_id, utc_now
from app.domain.runs.lifecycle import RunStatus
from app.domain.runs.models import BranchpointRun
from app.domain.verification.models import VerificationStatus
from app.domain.worlds.models import World, WorldVerdict

#: Statuses a run passes through *after* a human has approved it. Re-submitting
#: an approval for a run in one of these is a duplicate, not a new decision.
_ALREADY_DECIDED_STATUSES = frozenset(
    {
        RunStatus.APPROVED,
        RunStatus.COMMITTING,
        RunStatus.VERIFYING,
        RunStatus.SUCCEEDED,
    }
)


class ApprovalError(ApplicationError):
    """Base class for refusals of a human approval submission."""


class ApprovalNotAvailableError(ApprovalError):
    """Raised when a run is not at the approval gate."""


class ApprovalMismatchError(ApprovalError):
    """Raised when the client approved something other than what is recommended.

    Never resolved in the client's favour: a mismatch means the browser and the
    server disagree about what is on the table, and the safe reading is that the
    human was looking at something stale.
    """


class CommitFailedError(ApprovalError):
    """Raised when the approved commit did not reach a verified success."""


class ApprovalCoordinator:
    """Coordinates one human approval and the commit it authorizes."""

    def __init__(
        self,
        *,
        orchestrator: BranchpointOrchestrator,
        repository: RunRepository,
        events: EventSink,
        commit_operator: CommitOperator,
    ) -> None:
        self._orchestrator = orchestrator
        self._repository = repository
        self._events = events
        self._commit_operator = commit_operator

    async def reject(self, run_id: str, *, actor: str, reason: str = "") -> BranchpointRun:
        """Record a human's refusal of the recommended world.

        A governance decision, not a safety one. BRANCHPOINT already found this
        world survivable; a human is declining to act on it anyway, and that is
        a different fact from a veto — no evidence changes, no world verdict
        changes, and nothing is reproduced.

        Deliberately shares no step with :meth:`approve`. There is no path from
        here to the commit operator or the capability store, so a rejection
        cannot commit by any sequence of events: the run leaves
        ``AWAITING_APPROVAL`` for the terminal ``REJECTED``, which every commit
        gate already refuses.

        Idempotent in the same shape as approval: a decision already recorded is
        returned as it stands rather than recorded twice.
        """
        run = await self._require_run(run_id)

        if run.approval is not None and run.approval.status is ApprovalStatus.REJECTED:
            return run

        if run.status is not RunStatus.AWAITING_APPROVAL:
            raise ApprovalNotAvailableError(
                f"run {run.run_id} is {run.status}; only a run awaiting approval may be rejected"
            )
        if run.approval is None or run.approval.status is not ApprovalStatus.PENDING:
            raise ApprovalNotAvailableError(f"run {run.run_id} has no pending approval to decide")

        # The domain already knows how to decide an approval either way; this
        # has never had a caller for the refusing half.
        rejected = await self._orchestrator.decide_approval(
            run.run_id, approved=False, actor=actor, reason=reason
        )
        await self._emit_run_rejected(rejected, actor)
        return rejected

    async def approve(
        self,
        run_id: str,
        *,
        actor: str,
        expected_world_id: str | None = None,
        expected_action_id: str | None = None,
        expected_action_fingerprint: str | None = None,
    ) -> BranchpointRun:
        """Record a human approval and carry it through commit and verification.

        Idempotent: re-submitting an approval for a run that a human already
        approved returns the run's current state without approving, committing,
        or mutating anything a second time.
        """
        run = await self._require_run(run_id)

        if run.status in _ALREADY_DECIDED_STATUSES:
            self._assert_expectations_match(
                run, expected_world_id, expected_action_id, expected_action_fingerprint
            )
            return run

        world = self._assert_approvable(run)
        self._assert_expectations_match(
            run, expected_world_id, expected_action_id, expected_action_fingerprint
        )

        run = await self._orchestrator.decide_approval(
            run.run_id, approved=True, actor=actor, reason="approved by human in BRANCHPOINT"
        )

        report = await self._commit_operator.commit(run, world)
        await self._emit_operator_report(run.run_id, world.world_id, report)

        committed = await self._require_run(run.run_id)
        self._assert_committed(committed, report)
        return committed

    # ----- gates -------------------------------------------------------------

    def _assert_approvable(self, run: BranchpointRun) -> World:
        """Return the world a human may approve, or refuse to offer one.

        Only the comparator's own recommendation is approvable, and only while
        it still survives. Everything here re-derives from stored run state; the
        client contributes nothing to this decision.
        """
        if run.status is not RunStatus.AWAITING_APPROVAL:
            raise ApprovalNotAvailableError(
                f"run {run.run_id} is {run.status}; only a run awaiting approval may be approved"
            )
        approval = run.approval
        if approval is None or approval.status is not ApprovalStatus.PENDING:
            raise ApprovalNotAvailableError(f"run {run.run_id} has no pending approval to decide")
        if run.comparison is None or run.comparison.recommended_world_id is None:
            raise ApprovalNotAvailableError(f"run {run.run_id} has no comparator-recommended world")
        if approval.selected_world_id != run.comparison.recommended_world_id:
            raise ApprovalMismatchError(
                f"run {run.run_id} has a pending approval for {approval.selected_world_id}, "
                f"but comparison recommends {run.comparison.recommended_world_id}"
            )

        world = run.require_world(approval.selected_world_id)
        if world.verdict is not WorldVerdict.SURVIVED:
            raise ApprovalMismatchError(
                f"world {world.world_id} has verdict {world.verdict} and cannot be approved"
            )
        if world.candidate_action.action_id != approval.action_id:
            raise ApprovalMismatchError(
                f"world {world.world_id} now carries action "
                f"{world.candidate_action.action_id}, not the reviewed {approval.action_id}"
            )
        if world.candidate_action.fingerprint() != approval.action_fingerprint:
            raise ApprovalMismatchError(
                f"action {approval.action_id} changed after it was presented for approval"
            )
        return world

    @staticmethod
    def _assert_expectations_match(
        run: BranchpointRun,
        expected_world_id: str | None,
        expected_action_id: str | None,
        expected_action_fingerprint: str | None,
    ) -> None:
        """Check what the client *believes* it is approving against the truth.

        These fields are confirmations, never instructions: a client that names
        a different world or action is refused, not obeyed.
        """
        approval = run.approval
        if approval is None:
            raise ApprovalNotAvailableError(f"run {run.run_id} has no approval to confirm")

        if expected_world_id is not None and expected_world_id != approval.selected_world_id:
            raise ApprovalMismatchError(
                f"approval is for world {approval.selected_world_id}, "
                f"not the submitted {expected_world_id}"
            )
        if expected_action_id is not None and expected_action_id != approval.action_id:
            raise ApprovalMismatchError(
                f"approval is for action {approval.action_id}, "
                f"not the submitted {expected_action_id}"
            )
        if (
            expected_action_fingerprint is not None
            and expected_action_fingerprint != approval.action_fingerprint
        ):
            raise ApprovalMismatchError(
                "the submitted action fingerprint does not match the approved action"
            )

    @staticmethod
    def _assert_committed(run: BranchpointRun, report: CommitOperatorReport) -> None:
        """Refuse to report success unless reality was mutated and verified."""
        receipt = run.commit_receipt
        if receipt is None or receipt.status is not CommitStatus.SUCCEEDED:
            raise CommitFailedError(
                f"run {run.run_id} is {run.status} and has no successful commit "
                f"({report.detail or 'the destructive tool did not commit'})"
            )
        if run.verification is None or run.verification.status is not VerificationStatus.PASSED:
            status = run.verification.status if run.verification else "NOT_RUN"
            raise CommitFailedError(f"run {run.run_id} committed but verification is {status}")

    # ----- internals ---------------------------------------------------------

    async def _require_run(self, run_id: str) -> BranchpointRun:
        run = await self._repository.get(run_id)
        if run is None:
            raise RunNotFoundError(run_id)
        return run

    async def _emit_run_rejected(self, run: BranchpointRun, actor: str) -> None:
        """Close the run's timeline the way every other terminal path does.

        ``decide_approval`` already emitted ``APPROVAL_REJECTED`` — who decided
        and why. This is the run *ending*, which the orchestrator emits for its
        own rejection paths too, so a reader scanning for how a run finished
        finds the same event whatever refused it.
        """
        await self._events.emit(
            RunEvent(
                event_id=new_id("evt"),
                run_id=run.run_id,
                world_id=run.approval.selected_world_id if run.approval else None,
                event_type=RunEventType.RUN_REJECTED,
                summary=f"human rejection by {actor}; nothing was committed",
                occurred_at=utc_now(),
            )
        )

    async def _emit_operator_report(
        self, run_id: str, world_id: str, report: CommitOperatorReport
    ) -> None:
        """Record which TrueForge session carried the destructive call.

        Audit metadata around the commit, not a second COMMIT_STARTED: the
        orchestrator already emits the commit and verification lifecycle events.
        """
        await self._events.emit(
            RunEvent(
                event_id=new_id("evt"),
                run_id=run_id,
                world_id=world_id,
                event_type=RunEventType.TRUEFORGE_SESSION_CREATED,
                summary=f"{report.detail or 'commit operator session'}",
                occurred_at=utc_now(),
                payload={
                    "purpose": "COMMIT_OPERATOR",
                    "trueforge_session_id": report.session_id,
                    "tool_called": report.tool_called,
                },
            )
        )
