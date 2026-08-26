"""Deterministic coordination of a BRANCHPOINT run.

The orchestrator owns sequencing and state transitions only. Every capability
that touches the outside world arrives through a port, so the whole lifecycle is
exercisable with in-memory test doubles and no network.
"""

from collections.abc import Awaitable, Callable
from datetime import datetime

from app.application.errors import PortNotConfiguredError, RunNotFoundError
from app.application.ports import (
    AdversarialTester,
    CandidatePlanner,
    EventSink,
    RealityMutator,
    RealityReader,
    RealityVerifier,
    RunRepository,
    WorldExecutor,
)
from app.application.world_engine.comparator import compare_worlds
from app.domain.approvals.rules import assert_commit_allowed, build_approval_request
from app.domain.commits.models import CommitReceipt, CommitStatus
from app.domain.errors import InvariantViolationError
from app.domain.events import RunEvent, RunEventType
from app.domain.incidents.models import Incident
from app.domain.primitives import new_id, utc_now
from app.domain.runs.lifecycle import RunStatus
from app.domain.runs.models import BranchpointRun
from app.domain.verification.models import (
    VerificationResult,
    VerificationStatus,
    derive_verification_status,
)
from app.domain.worlds.lifecycle import WorldStatus
from app.domain.worlds.models import World, WorldVerdict
from app.domain.worlds.verdicts import counterexample_vetoes, derive_verdict


class BranchpointOrchestrator:
    """Drives one run through observe → plan → fork → execute → attack → compare
    → approve → commit → verify."""

    def __init__(
        self,
        *,
        repository: RunRepository,
        events: EventSink,
        reality_reader: RealityReader | None = None,
        planner: CandidatePlanner | None = None,
        world_executor: WorldExecutor | None = None,
        adversarial_tester: AdversarialTester | None = None,
        mutator: RealityMutator | None = None,
        verifier: RealityVerifier | None = None,
        clock: Callable[[], datetime] = utc_now,
        id_factory: Callable[[str], str] = new_id,
    ) -> None:
        self._repository = repository
        self._events = events
        self._reality_reader = reality_reader
        self._planner = planner
        self._world_executor = world_executor
        self._adversarial_tester = adversarial_tester
        self._mutator = mutator
        self._verifier = verifier
        self._clock = clock
        self._id = id_factory

    @property
    def repository(self) -> RunRepository:
        """Read access to the run store this orchestrator writes through.

        Exposed so a caller that must record an outcome *about* a run it was
        driving — the background runner failing a run whose pipeline raised —
        can do so through the same store, rather than keeping a second handle
        that could drift from this one.
        """
        return self._repository

    # ----- run steps ---------------------------------------------------------

    async def create_run(self, incident: Incident) -> BranchpointRun:
        """Open a run for ``incident``."""
        now = self._clock()
        run = BranchpointRun.create(run_id=self._id("run"), incident=incident, at=now)
        await self._repository.save(run)
        await self._emit(
            run, RunEventType.RUN_CREATED, f"run opened for incident {incident.incident_id}"
        )
        return run

    async def observe(self, run_id: str) -> BranchpointRun:
        """Read structured observations of reality into the run."""
        run = await self._require_run(run_id)
        reader = _require_port(self._reality_reader, "RealityReader")

        run = await self._store(run.transition_to(RunStatus.OBSERVING, at=self._clock()))
        observed = await self._guard(
            run, "observation failed", lambda: reader.observe(run.incident)
        )
        run = await self._store(run.with_observation(observed, at=self._clock()))
        await self._emit(
            run,
            RunEventType.OBSERVATION_COMPLETED,
            f"observed {len(observed.metrics)} metric(s) from {observed.source}",
        )
        return run

    async def plan(self, run_id: str) -> BranchpointRun:
        """Ask the planner for candidate actions worth testing."""
        run = await self._require_run(run_id)
        planner = _require_port(self._planner, "CandidatePlanner")
        if run.observed_state is None:
            raise InvariantViolationError(
                "planning follows observation", f"run {run.run_id} has no observed state"
            )
        observed = run.observed_state

        run = await self._store(run.transition_to(RunStatus.PLANNING, at=self._clock()))
        candidates = await self._guard(
            run,
            "planning failed",
            lambda: planner.plan(run.incident, observed, run_id=run.run_id),
        )
        if not candidates:
            run = await self._store(run.transition_to(RunStatus.REJECTED, at=self._clock()))
            await self._emit(run, RunEventType.RUN_REJECTED, "no candidate actions were proposed")
            return run

        run = await self._store(run.with_candidates(tuple(candidates), at=self._clock()))
        await self._emit(
            run,
            RunEventType.CANDIDATES_PLANNED,
            f"{len(run.candidate_actions)} candidate action(s) proposed",
        )
        return run

    async def fork(self, run_id: str) -> BranchpointRun:
        """Create one counterfactual world per candidate action."""
        run = await self._require_run(run_id)
        now = self._clock()
        run = run.transition_to(RunStatus.FORKING, at=now)
        worlds = tuple(
            World.create(
                world_id=self._id("world"),
                run_id=run.run_id,
                candidate_action=action,
                at=now,
            )
            for action in run.candidate_actions
        )
        run = await self._store(run.with_worlds(worlds, at=now))
        for world in worlds:
            await self._emit(
                run,
                RunEventType.WORLD_CREATED,
                f"world forked for action {world.candidate_action.name}",
                world_id=world.world_id,
            )
        return run

    async def execute_worlds(self, run_id: str) -> BranchpointRun:
        """Execute every candidate action inside its own world.

        Worlds are executed one at a time in Phase 1; the executor port takes a
        single world so this loop can become concurrent without contract changes.
        """
        run = await self._require_run(run_id)
        executor = _require_port(self._world_executor, "WorldExecutor")
        run = await self._store(run.transition_to(RunStatus.EXECUTING_WORLDS, at=self._clock()))

        for world in run.worlds:
            executing = world.transition_to(WorldStatus.PREPARING, at=self._clock()).transition_to(
                WorldStatus.EXECUTING, at=self._clock()
            )
            run = await self._store(run.replace_world(executing, at=self._clock()))
            await self._emit(
                run,
                RunEventType.WORLD_EXECUTION_STARTED,
                f"executing {executing.candidate_action.name} counterfactually",
                world_id=executing.world_id,
            )
            try:
                report = await executor.execute(executing)
            except Exception as exc:  # one broken world must not abort the run
                settled = executing.settle(
                    WorldVerdict.EXECUTION_FAILED, f"executor error: {exc}", at=self._clock()
                )
                run = await self._store(run.replace_world(settled, at=self._clock()))
                await self._emit(
                    run,
                    RunEventType.WORLD_EXECUTION_COMPLETED,
                    f"execution failed: {exc}",
                    world_id=settled.world_id,
                )
                continue

            executed = executing.record_execution(report, at=self._clock())
            run = await self._store(run.replace_world(executed, at=self._clock()))
            await self._emit(
                run,
                RunEventType.WORLD_EXECUTION_COMPLETED,
                report.outcome.summary or "counterfactual execution completed",
                world_id=executed.world_id,
            )
        return run

    async def run_adversarial_tests(self, run_id: str) -> BranchpointRun:
        """Attack every executed world and settle its evidence-backed verdict."""
        run = await self._require_run(run_id)
        tester = _require_port(self._adversarial_tester, "AdversarialTester")
        run = await self._store(run.transition_to(RunStatus.ADVERSARIAL_TESTING, at=self._clock()))

        for world in run.worlds:
            if world.is_terminal:
                continue
            attacking = world.transition_to(WorldStatus.ATTACKING, at=self._clock())
            await self._emit(
                run,
                RunEventType.DOPPELGANGER_STARTED,
                f"attacking {attacking.candidate_action.name}",
                world_id=attacking.world_id,
            )
            try:
                report = await tester.attack(attacking)
            except Exception as exc:  # an attacker failure must not fabricate survival
                settled = attacking.settle(
                    WorldVerdict.INCONCLUSIVE,
                    f"adversarial testing error: {exc}",
                    at=self._clock(),
                )
                run = await self._store(run.replace_world(settled, at=self._clock()))
                continue

            attacked = attacking.record_attacks(report, at=self._clock())
            index = attacked.evidence_by_id
            for attack in report.counterexamples:
                if counterexample_vetoes(attack, index):
                    await self._emit(
                        run,
                        RunEventType.COUNTEREXAMPLE_REPRODUCED,
                        f"reproduced: {attack.title}",
                        world_id=attacked.world_id,
                    )

            evaluating = attacked.transition_to(WorldStatus.EVALUATING, at=self._clock())
            verdict, reason = derive_verdict(evaluating)
            settled = evaluating.settle(verdict, reason, at=self._clock())
            run = await self._store(run.replace_world(settled, at=self._clock()))
            await self._emit(
                run,
                RunEventType.WORLD_SURVIVED
                if verdict is WorldVerdict.SURVIVED
                else RunEventType.WORLD_VETOED,
                reason,
                world_id=settled.world_id,
            )
        return run

    async def compare(self, run_id: str) -> BranchpointRun:
        """Compare the worlds deterministically."""
        run = await self._require_run(run_id)
        run = run.transition_to(RunStatus.COMPARING, at=self._clock())
        comparison = compare_worlds(run.worlds)
        run = await self._store(run.with_comparison(comparison, at=self._clock()))
        await self._emit(run, RunEventType.COMPARISON_COMPLETED, comparison.summary)
        return run

    async def request_approval(self, run_id: str, world_id: str | None = None) -> BranchpointRun:
        """Ask a human to approve one surviving world.

        When comparison recommends nothing — because nothing survived or because
        the survivors are tied — the run is rejected rather than guessing.
        """
        run = await self._require_run(run_id)
        if run.comparison is None:
            raise InvariantViolationError(
                "approval follows comparison", f"run {run.run_id} has no comparison result"
            )

        target = world_id or run.comparison.recommended_world_id
        if target is None:
            run = await self._store(run.transition_to(RunStatus.REJECTED, at=self._clock()))
            await self._emit(run, RunEventType.RUN_REJECTED, run.comparison.summary)
            return run

        approval = build_approval_request(
            run, target, approval_id=self._id("approval"), requested_at=self._clock()
        )
        run = run.with_approval(approval, at=self._clock())
        run = await self._store(run.transition_to(RunStatus.AWAITING_APPROVAL, at=self._clock()))
        await self._emit(
            run,
            RunEventType.APPROVAL_REQUESTED,
            f"approval requested for world {target}",
            world_id=target,
        )
        return run

    async def decide_approval(
        self, run_id: str, *, approved: bool, actor: str, reason: str = ""
    ) -> BranchpointRun:
        """Record the human decision on the pending approval."""
        run = await self._require_run(run_id)
        if run.approval is None or run.status is not RunStatus.AWAITING_APPROVAL:
            raise InvariantViolationError(
                "decision requires a pending approval",
                f"run {run.run_id} is {run.status} with approval {run.approval is not None}",
            )

        decided = run.approval.decide(
            approved=approved, actor=actor, reason=reason, at=self._clock()
        )
        run = run.with_approval(decided, at=self._clock())
        run = await self._store(
            run.transition_to(
                RunStatus.APPROVED if approved else RunStatus.REJECTED, at=self._clock()
            )
        )
        await self._emit(
            run,
            RunEventType.APPROVAL_GRANTED if approved else RunEventType.APPROVAL_REJECTED,
            f"{actor} {'approved' if approved else 'rejected'} world {decided.selected_world_id}",
            world_id=decided.selected_world_id,
        )
        return run

    async def commit(self, run_id: str) -> BranchpointRun:
        """Apply exactly the approved action to reality."""
        run = await self._require_run(run_id)
        mutator = _require_port(self._mutator, "RealityMutator")
        world = assert_commit_allowed(run)
        approval = run.approval
        assert approval is not None  # guaranteed by assert_commit_allowed

        started_at = self._clock()
        receipt = CommitReceipt(
            commit_id=self._id("commit"),
            run_id=run.run_id,
            world_id=world.world_id,
            action_id=world.candidate_action.action_id,
            action_fingerprint=approval.action_fingerprint,
            started_at=started_at,
        )
        run = run.transition_to(RunStatus.COMMITTING, at=started_at)
        run = await self._store(run.with_commit_receipt(receipt, at=started_at))
        await self._emit(
            run,
            RunEventType.COMMIT_STARTED,
            f"committing {world.candidate_action.name}",
            world_id=world.world_id,
        )

        try:
            operations = await mutator.apply(run, world)
        except Exception as exc:
            failed = receipt.fail(f"mutator error: {exc}", at=self._clock())
            run = run.with_commit_receipt(failed, at=self._clock())
            await self._store(run.fail(f"commit failed: {exc}", at=self._clock()))
            raise

        completed = receipt.complete(tuple(operations), at=self._clock())
        run = await self._store(run.with_commit_receipt(completed, at=self._clock()))
        await self._emit(
            run,
            RunEventType.COMMIT_COMPLETED,
            f"commit {completed.status} with {len(completed.operations)} operation(s)",
            world_id=world.world_id,
        )
        if completed.status is not CommitStatus.SUCCEEDED:
            run = await self._store(run.fail("commit did not succeed", at=self._clock()))
        return run

    async def verify(self, run_id: str) -> BranchpointRun:
        """Independently check reality after the commit.

        A successful commit is not success: only verification decides that.
        """
        run = await self._require_run(run_id)
        verifier = _require_port(self._verifier, "RealityVerifier")
        commit_receipt = run.commit_receipt
        if commit_receipt is None or commit_receipt.status is not CommitStatus.SUCCEEDED:
            raise InvariantViolationError(
                "verification follows a successful commit",
                f"run {run.run_id} has no succeeded commit receipt",
            )

        started_at = self._clock()
        run = await self._store(run.transition_to(RunStatus.VERIFYING, at=started_at))
        await self._emit(
            run,
            RunEventType.VERIFICATION_STARTED,
            f"independently verifying commit {commit_receipt.commit_id}",
        )
        checks = await self._guard(
            run, "verification failed", lambda: verifier.verify(run, commit_receipt)
        )
        status = derive_verification_status(tuple(checks))
        result = VerificationResult(
            verification_id=self._id("verification"),
            run_id=run.run_id,
            commit_id=commit_receipt.commit_id,
            status=status,
            checks=tuple(checks),
            evidence_ids=tuple(
                check.evidence_id for check in checks if check.evidence_id is not None
            ),
            started_at=started_at,
            completed_at=self._clock(),
        )
        run = await self._store(run.with_verification(result, at=self._clock()))
        await self._emit(run, RunEventType.VERIFICATION_COMPLETED, f"verification {status}")

        if status is VerificationStatus.PASSED:
            run = await self._store(run.transition_to(RunStatus.SUCCEEDED, at=self._clock()))
            await self._emit(
                run,
                RunEventType.RUN_SUCCEEDED,
                "committed action verified in reality",
                world_id=run.selected_world_id,
            )
            return run
        return await self._store(run.fail(f"verification {status}", at=self._clock()))

    async def drive_to_approval(self, incident: Incident) -> BranchpointRun:
        """Run every deterministic step up to the human approval gate."""
        run = await self.create_run(incident)
        run = await self.observe(run.run_id)
        run = await self.plan(run.run_id)
        if run.is_terminal:
            return run
        run = await self.fork(run.run_id)
        run = await self.execute_worlds(run.run_id)
        run = await self.run_adversarial_tests(run.run_id)
        run = await self.compare(run.run_id)
        return await self.request_approval(run.run_id)

    # ----- internals ---------------------------------------------------------

    async def _require_run(self, run_id: str) -> BranchpointRun:
        run = await self._repository.get(run_id)
        if run is None:
            raise RunNotFoundError(run_id)
        return run

    async def _store(self, run: BranchpointRun) -> BranchpointRun:
        await self._repository.save(run)
        return run

    async def _guard[T](
        self, run: BranchpointRun, description: str, call: Callable[[], Awaitable[T]]
    ) -> T:
        """Await ``call``, failing the run with an explicit reason if it raises."""
        try:
            return await call()
        except Exception as exc:
            failed = run.fail(f"{description}: {exc}", at=self._clock())
            await self._repository.save(failed)
            await self._emit(failed, RunEventType.RUN_FAILED, failed.failure_reason)
            raise

    async def _emit(
        self,
        run: BranchpointRun,
        event_type: RunEventType,
        summary: str,
        *,
        world_id: str | None = None,
    ) -> None:
        await self._events.emit(
            RunEvent(
                event_id=self._id("evt"),
                run_id=run.run_id,
                world_id=world_id,
                event_type=event_type,
                summary=summary,
                occurred_at=self._clock(),
            )
        )


def _require_port[T](port: T | None, name: str) -> T:
    """Return ``port`` or raise a clear error naming the missing capability."""
    if port is None:
        raise PortNotConfiguredError(name)
    return port
