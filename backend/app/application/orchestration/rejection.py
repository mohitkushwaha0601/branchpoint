"""Human rejection of the recommended world.

Deliberately its own coordinator, and deliberately not a method on
:class:`~app.application.orchestration.approval.ApprovalCoordinator`.

Rejection is a *fail-closed governance* operation. It records that a person
declined to act and moves the run to the terminal ``REJECTED`` state, which
every commit gate already refuses. It needs three deterministic things — the run
store, the event sink, and the domain orchestrator — and nothing else.

Approval, by contrast, has to carry the decision through a real commit: it
builds a TrueForge commit operator, which resolves a model. Sharing one
coordinator meant the *builder* for a rejection eagerly constructed that commit
operator, so declining an action required a configured model even though the
refusing code path never touched one. A rejection that cannot be recorded
without a model provider is not fail-closed, and in an environment with no model
configured — CI, or an operator's laptop — the safe half of the gate was the
half that broke.

So the dependency is removed structurally rather than guarded: there is no
commit operator on this object to reach, and no ``resolve_model`` call anywhere
in its construction.
"""

from app.application.errors import RunNotFoundError
from app.application.orchestration.approval import ApprovalNotAvailableError
from app.application.orchestration.orchestrator import BranchpointOrchestrator
from app.application.ports import EventSink, RunRepository
from app.domain.approvals.models import ApprovalStatus
from app.domain.events import RunEvent, RunEventType
from app.domain.primitives import new_id, utc_now
from app.domain.runs.lifecycle import RunStatus
from app.domain.runs.models import BranchpointRun


class HumanRejectionCoordinator:
    """Records one human refusal. Holds nothing that could commit."""

    def __init__(
        self,
        *,
        orchestrator: BranchpointOrchestrator,
        repository: RunRepository,
        events: EventSink,
    ) -> None:
        self._orchestrator = orchestrator
        self._repository = repository
        self._events = events

    async def reject(self, run_id: str, *, actor: str, reason: str = "") -> BranchpointRun:
        """Record a human's refusal of the recommended world.

        A governance decision, not a safety one. BRANCHPOINT already found this
        world survivable; a human is declining to act on it anyway, and that is
        a different fact from a veto — no evidence changes, no world verdict
        changes, and nothing is reproduced.

        There is no path from here to the commit operator or the capability
        store, so a rejection cannot commit by any sequence of events: the run
        leaves ``AWAITING_APPROVAL`` for the terminal ``REJECTED``, which every
        commit gate already refuses.

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
