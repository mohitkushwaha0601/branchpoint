"""Approval → capability → commit → verification, as a security boundary.

Every test here drives the *real* stack: the real orchestrator, the real
domain invariants, the real one-time capability store, and the real destructive
MCP tool over a real MCP session. Only the TrueForge agent is stood in for —
by a double that calls the same sanctioned tool the live commit operator calls,
so the mutation path under test is the production one, not a shortcut.

The property being defended throughout: *after a human approves, nothing —
model, agent, or browser — can choose, modify, or substitute the action.*
"""

import pytest

from app.application.orchestration.approval import (
    ApprovalCoordinator,
    ApprovalMismatchError,
    ApprovalNotAvailableError,
    CommitFailedError,
)
from app.application.orchestration.orchestrator import BranchpointOrchestrator
from app.application.ports import CommitOperatorReport
from app.domain.commits.models import CommitStatus
from app.domain.errors import InvariantViolationError
from app.domain.events import RunEventType
from app.domain.incidents.models import Incident, IncidentSeverity
from app.domain.primitives import new_id, utc_now
from app.domain.runs.lifecycle import RunStatus
from app.domain.verification.models import VerificationStatus
from app.domain.worlds.models import WorldVerdict
from app.infrastructure.demo.adapters import (
    DemoRealityMutator,
    DemoRealityReader,
    DemoRealityVerifier,
    DemoWorldExecutor,
)
from app.infrastructure.demo.capability import (
    CapabilityAlreadyUsedError,
    CapabilityMismatchError,
    CapabilityNotFoundError,
    CapabilityStore,
)
from app.infrastructure.demo.engine import DemoProductionEngine
from app.infrastructure.demo.hero import HeroAdversarialTester, HeroCandidatePlanner
from app.infrastructure.persistence.memory import InMemoryEventSink, InMemoryRunRepository
from app.mcp.server import COMMIT_TOOL_NAME, build_mcp_server
from tests.mcp.conftest import MCPTestHarness, mcp_session
from tests.trueforge.conftest import CommitHarness


def incident() -> Incident:
    return Incident(
        incident_id=new_id("incident"),
        title="Checkout error rate at 41.3%",
        goal="Return checkout error rate below 2%",
        severity=IncidentSeverity.CRITICAL,
        detected_at=utc_now(),
    )


class McpCommitOperator:
    """Stands in for the TrueForge commit operator.

    Calls the *real* destructive MCP tool over a real MCP session, which is
    exactly what the live operator's approved tool call does. Every argument is
    taken from the run and world BRANCHPOINT hands it, so an honest operator
    cannot introduce a substitution — the dishonest subclasses below do that
    deliberately.
    """

    def __init__(self, harness: MCPTestHarness) -> None:
        self._harness = harness
        self.calls: list[dict] = []

    def arguments(self, run, world) -> dict:
        """The arguments this operator will send. Overridden to misbehave."""
        return {
            "run_id": run.run_id,
            "world_id": world.world_id,
            "expected_action_id": world.candidate_action.action_id,
        }

    async def commit(self, run, world) -> CommitOperatorReport:
        arguments = self.arguments(run, world)
        self.calls.append(arguments)
        async with mcp_session(self._harness) as session:
            result = await session.call_tool(COMMIT_TOOL_NAME, arguments)
        return CommitOperatorReport(
            session_id="sess_fake",
            turn_id="turn_fake",
            tool_called=result.is_error is not True,
            detail=str(result.content[0].text)[:200] if result.content else "",
        )


class WrongWorldOperator(McpCommitOperator):
    """An operator that tries to commit a world the human did not approve."""

    def __init__(self, harness: MCPTestHarness, other_world_id: str) -> None:
        super().__init__(harness)
        self._other = other_world_id

    def arguments(self, run, world) -> dict:
        return {"run_id": run.run_id, "world_id": self._other}


class WrongActionOperator(McpCommitOperator):
    """An operator that claims the approved world carries a different action."""

    def arguments(self, run, world) -> dict:
        return {
            "run_id": run.run_id,
            "world_id": world.world_id,
            "expected_action_id": "action_substituted",
        }


class TamperingOperator(McpCommitOperator):
    """An operator that rewrites the approved action before invoking the commit.

    Models the worst case: something with write access to run state changes
    what was approved *after* the human approved it.
    """

    def __init__(self, harness: MCPTestHarness, repository: InMemoryRunRepository) -> None:
        super().__init__(harness)
        self._repository = repository

    async def commit(self, run, world) -> CommitOperatorReport:
        tampered_action = world.candidate_action.model_copy(
            update={"parameters": {"flag_key": "SOMETHING_ELSE"}}
        )
        tampered_world = world.model_copy(update={"candidate_action": tampered_action})
        await self._repository.save(run.replace_world(tampered_world))
        return await super().commit(run, world)


class SilentOperator(McpCommitOperator):
    """An operator that never calls the tool at all."""

    async def commit(self, run, world) -> CommitOperatorReport:
        self.calls.append({})
        return CommitOperatorReport(tool_called=False, detail="declined to call the tool")


class ReplayingOperator(McpCommitOperator):
    """An operator that calls the sanctioned commit twice in one turn."""

    async def commit(self, run, world) -> CommitOperatorReport:
        first = await super().commit(run, world)
        self.second = await super().commit(run, world)
        return first


def build_coordinator(harness: CommitHarness, operator) -> ApprovalCoordinator:
    """Wire the coordinator over an existing harness and a commit operator."""
    return ApprovalCoordinator(
        orchestrator=harness.orchestrator,
        repository=harness.mcp.run_repository,
        events=harness.events,
        commit_operator=operator,
    )


async def flag_enabled(harness: CommitHarness) -> bool:
    """Whether the pricing feature flag is still on in demo reality."""
    return (await harness.engine.reality()).pricing_flag.enabled


async def settle_recommended_world(harness: CommitHarness, run, verdict: WorldVerdict):
    """Force the recommended world to a different verdict in storage."""
    world = run.require_world(run.comparison.recommended_world_id)
    replaced = run.replace_world(world.model_copy(update={"verdict": verdict}))
    await harness.mcp.run_repository.save(replaced)
    return replaced


# ----- 1-4: what may be approved, and when -----------------------------------


async def test_cannot_approve_before_awaiting_approval(commit_harness: CommitHarness) -> None:
    """1. A run that has not reached the gate has nothing to approve."""
    run = await commit_harness.orchestrator.create_run(incident())
    operator = McpCommitOperator(commit_harness.mcp)

    with pytest.raises(ApprovalNotAvailableError, match="only a run awaiting approval"):
        await build_coordinator(commit_harness, operator).approve(run.run_id, actor="human")

    assert operator.calls == []
    assert await flag_enabled(commit_harness) is True


async def test_cannot_approve_a_vetoed_world(commit_harness: CommitHarness) -> None:
    """2. A world that lost its survival cannot be approved, gate reached or not."""
    run = await commit_harness.drive_to_approval(incident())
    await settle_recommended_world(commit_harness, run, WorldVerdict.VETOED)
    operator = McpCommitOperator(commit_harness.mcp)

    with pytest.raises(ApprovalMismatchError, match="VETOED"):
        await build_coordinator(commit_harness, operator).approve(run.run_id, actor="human")

    assert operator.calls == []
    assert await flag_enabled(commit_harness) is True


async def test_cannot_approve_an_inconclusive_world(commit_harness: CommitHarness) -> None:
    """3. Inconclusive is not survival: an unproven world is not approvable."""
    run = await commit_harness.drive_to_approval(incident())
    await settle_recommended_world(commit_harness, run, WorldVerdict.INCONCLUSIVE)
    operator = McpCommitOperator(commit_harness.mcp)

    with pytest.raises(ApprovalMismatchError, match="INCONCLUSIVE"):
        await build_coordinator(commit_harness, operator).approve(run.run_id, actor="human")

    assert operator.calls == []
    assert await flag_enabled(commit_harness) is True


async def test_only_the_recommended_surviving_world_is_approvable(
    commit_harness: CommitHarness,
) -> None:
    """4. On the hero path, exactly one world is on the table — the recommended one."""
    run = await commit_harness.drive_to_approval(incident())
    recommended = run.comparison.recommended_world_id
    other = next(w.world_id for w in run.worlds if w.world_id != recommended)

    assert run.approval.selected_world_id == recommended
    assert run.require_world(recommended).verdict is WorldVerdict.SURVIVED

    operator = McpCommitOperator(commit_harness.mcp)
    with pytest.raises(ApprovalMismatchError, match="not the submitted"):
        await build_coordinator(commit_harness, operator).approve(
            run.run_id, actor="human", expected_world_id=other
        )

    assert operator.calls == []
    assert await flag_enabled(commit_harness) is True


# ----- 5-9: the approval binds, and the binding is not negotiable ------------


async def test_approval_binds_exact_run_world_and_action(commit_harness: CommitHarness) -> None:
    """5. The approval names one run, one world, one action — not a category."""
    run = await commit_harness.drive_to_approval(incident())
    world = run.require_world(run.comparison.recommended_world_id)

    approval = run.approval
    assert approval.run_id == run.run_id
    assert approval.selected_world_id == world.world_id
    assert approval.action_id == world.candidate_action.action_id


async def test_approval_binds_the_exact_action_fingerprint(
    commit_harness: CommitHarness,
) -> None:
    """6. The binding covers action *content*, not just its id."""
    run = await commit_harness.drive_to_approval(incident())
    world = run.require_world(run.comparison.recommended_world_id)

    assert run.approval.action_fingerprint == world.candidate_action.fingerprint()

    # Same id, different parameters -> different fingerprint.
    altered = world.candidate_action.model_copy(update={"parameters": {"flag_key": "OTHER"}})
    assert altered.action_id == world.candidate_action.action_id
    assert altered.fingerprint() != run.approval.action_fingerprint


async def test_action_modified_after_approval_is_rejected(
    commit_harness: CommitHarness,
) -> None:
    """7. Rewriting the action after approval refuses the commit, it does not commit it."""
    run = await commit_harness.drive_to_approval(incident())
    operator = TamperingOperator(commit_harness.mcp, commit_harness.mcp.run_repository)

    with pytest.raises(CommitFailedError):
        await build_coordinator(commit_harness, operator).approve(run.run_id, actor="human")

    assert await flag_enabled(commit_harness) is True


async def test_wrong_world_is_rejected_by_the_commit_tool(
    commit_harness: CommitHarness,
) -> None:
    """8. An agent that redirects the commit is refused by the tool itself."""
    run = await commit_harness.drive_to_approval(incident())
    recommended = run.comparison.recommended_world_id
    other = next(w.world_id for w in run.worlds if w.world_id != recommended)
    operator = WrongWorldOperator(commit_harness.mcp, other)

    with pytest.raises(CommitFailedError):
        await build_coordinator(commit_harness, operator).approve(run.run_id, actor="human")

    assert await flag_enabled(commit_harness) is True


async def test_wrong_action_is_rejected_by_the_commit_tool(
    commit_harness: CommitHarness,
) -> None:
    """9. Claiming a different action id is refused before anything mutates."""
    run = await commit_harness.drive_to_approval(incident())
    operator = WrongActionOperator(commit_harness.mcp)

    with pytest.raises(CommitFailedError):
        await build_coordinator(commit_harness, operator).approve(run.run_id, actor="human")

    assert await flag_enabled(commit_harness) is True


# ----- 10-15: the one-time capability ----------------------------------------


async def approved_capability(harness: CommitHarness):
    """Drive to approval, grant it, and issue one real capability."""
    run = await harness.drive_to_approval(incident())
    run = await harness.orchestrator.decide_approval(run.run_id, approved=True, actor="human")
    issued = await harness.mcp.capability_store.issue_for_approved_run(run)
    world = run.require_world(run.approval.selected_world_id)
    return run, world, issued


async def test_missing_capability_is_rejected(commit_harness: CommitHarness) -> None:
    """10. No token is not a special case — it is a rejection."""
    with pytest.raises(CapabilityNotFoundError):
        await commit_harness.mcp.capability_store.peek("")


async def test_invalid_capability_is_rejected(commit_harness: CommitHarness) -> None:
    """11. A fabricated token names nothing and authorizes nothing."""
    run, world, _ = await approved_capability(commit_harness)

    with pytest.raises(CapabilityNotFoundError):
        await commit_harness.mcp.capability_store.consume(
            "cap_forged.not-a-real-secret",
            run_id=run.run_id,
            world_id=world.world_id,
            action_id=world.candidate_action.action_id,
            action_fingerprint=world.candidate_action.fingerprint(),
        )


async def test_capability_for_another_run_is_rejected(commit_harness: CommitHarness) -> None:
    """12. A valid token is still refused outside the run it was issued for."""
    run, world, issued = await approved_capability(commit_harness)

    with pytest.raises(CapabilityMismatchError) as raised:
        await commit_harness.mcp.capability_store.consume(
            issued.token,
            run_id="run_someone_elses",
            world_id=world.world_id,
            action_id=world.candidate_action.action_id,
            action_fingerprint=world.candidate_action.fingerprint(),
        )
    assert raised.value.field == "run"
    assert await flag_enabled(commit_harness) is True


async def test_capability_for_another_world_is_rejected(commit_harness: CommitHarness) -> None:
    """13. Same run, different world: still refused."""
    run, world, issued = await approved_capability(commit_harness)
    other = next(w.world_id for w in run.worlds if w.world_id != world.world_id)

    with pytest.raises(CapabilityMismatchError) as raised:
        await commit_harness.mcp.capability_store.consume(
            issued.token,
            run_id=run.run_id,
            world_id=other,
            action_id=world.candidate_action.action_id,
            action_fingerprint=world.candidate_action.fingerprint(),
        )
    assert raised.value.field == "world"


async def test_capability_is_single_use(commit_harness: CommitHarness) -> None:
    """14. Spending a capability twice fails the second time, every time."""
    run, world, issued = await approved_capability(commit_harness)
    fields = {
        "run_id": run.run_id,
        "world_id": world.world_id,
        "action_id": world.candidate_action.action_id,
        "action_fingerprint": world.candidate_action.fingerprint(),
    }

    spent = await commit_harness.mcp.capability_store.consume(issued.token, **fields)
    assert spent.used_at is not None

    with pytest.raises(CapabilityAlreadyUsedError):
        await commit_harness.mcp.capability_store.consume(issued.token, **fields)


async def test_replayed_commit_is_rejected(commit_harness: CommitHarness) -> None:
    """15. Calling the sanctioned commit twice mutates reality exactly once."""
    run = await commit_harness.drive_to_approval(incident())
    operator = ReplayingOperator(commit_harness.mcp)

    approved = await build_coordinator(commit_harness, operator).approve(run.run_id, actor="human")

    assert approved.status is RunStatus.SUCCEEDED
    assert operator.second.tool_called is False
    assert len(operator.calls) == 2
    reality = await commit_harness.engine.reality()
    assert reality.pricing_flag.enabled is False


# ----- 16-20: the happy path, and the ways it must not be faked --------------


async def test_an_operator_that_never_commits_is_not_reported_as_success(
    commit_harness: CommitHarness,
) -> None:
    """A recorded approval is not a commit: silence fails loudly."""
    run = await commit_harness.drive_to_approval(incident())
    operator = SilentOperator(commit_harness.mcp)

    with pytest.raises(CommitFailedError, match="no successful commit"):
        await build_coordinator(commit_harness, operator).approve(run.run_id, actor="human")

    assert await flag_enabled(commit_harness) is True


async def test_duplicate_browser_approval_is_idempotent(commit_harness: CommitHarness) -> None:
    """16. A double-clicked approve button commits once, not twice."""
    run = await commit_harness.drive_to_approval(incident())
    operator = McpCommitOperator(commit_harness.mcp)
    coordinator = build_coordinator(commit_harness, operator)

    first = await coordinator.approve(run.run_id, actor="human")
    second = await coordinator.approve(run.run_id, actor="human")

    assert first.status is RunStatus.SUCCEEDED
    assert second.status is RunStatus.SUCCEEDED
    assert second.commit_receipt.commit_id == first.commit_receipt.commit_id
    assert len(operator.calls) == 1


async def test_mutation_happens_only_after_approval(commit_harness: CommitHarness) -> None:
    """17. Reality is untouched at the gate and changes only once approval is recorded."""
    run = await commit_harness.drive_to_approval(incident())

    assert run.status is RunStatus.AWAITING_APPROVAL
    assert await flag_enabled(commit_harness) is True

    approved = await build_coordinator(
        commit_harness, McpCommitOperator(commit_harness.mcp)
    ).approve(run.run_id, actor="human")

    assert approved.approval.is_granted is True
    assert await flag_enabled(commit_harness) is False


async def test_verification_requires_a_successful_commit(commit_harness: CommitHarness) -> None:
    """18. Verification cannot run — or pass — without a commit that succeeded."""
    run = await commit_harness.drive_to_approval(incident())
    await commit_harness.orchestrator.decide_approval(run.run_id, approved=True, actor="human")

    with pytest.raises(InvariantViolationError, match="verification follows a successful commit"):
        await commit_harness.orchestrator.verify(run.run_id)


async def test_failed_verification_cannot_produce_succeeded() -> None:
    """19. A commit that applies but does not verify is a failure, not a success."""
    harness = await _harness_with_failing_verifier()
    run = await harness.drive_to_approval(incident())
    operator = McpCommitOperator(harness.mcp)

    with pytest.raises(CommitFailedError, match="verification"):
        await build_coordinator(harness, operator).approve(run.run_id, actor="human")

    stored = await harness.mcp.run_repository.get(run.run_id)
    assert stored.verification.status is VerificationStatus.FAILED
    assert stored.status is RunStatus.FAILED
    assert stored.status is not RunStatus.SUCCEEDED


async def test_successful_verification_produces_succeeded(commit_harness: CommitHarness) -> None:
    """20. The whole point: approved, committed, independently verified, SUCCEEDED."""
    run = await commit_harness.drive_to_approval(incident())

    approved = await build_coordinator(
        commit_harness, McpCommitOperator(commit_harness.mcp)
    ).approve(run.run_id, actor="release-engineer")

    assert approved.status is RunStatus.SUCCEEDED
    assert approved.commit_receipt.status is CommitStatus.SUCCEEDED
    assert approved.verification.status is VerificationStatus.PASSED
    assert approved.approval.actor == "release-engineer"
    assert await flag_enabled(commit_harness) is False

    timeline = [event.event_type for event in await commit_harness.events.events_for(run.run_id)]
    for expected in (
        RunEventType.APPROVAL_REQUESTED,
        RunEventType.APPROVAL_GRANTED,
        RunEventType.COMMIT_STARTED,
        RunEventType.COMMIT_COMPLETED,
        RunEventType.VERIFICATION_STARTED,
        RunEventType.VERIFICATION_COMPLETED,
        RunEventType.RUN_SUCCEEDED,
    ):
        assert timeline.count(expected) == 1, f"{expected} should appear exactly once"


# ----- 21-23: no token leaks, no bypass, no early mutation -------------------


async def test_no_capability_token_reaches_the_model(commit_harness: CommitHarness) -> None:
    """21. Not in the instructions, not in the arguments, not in the tool's reply."""
    from app.infrastructure.trueforge.commit_operator import (
        COMMIT_OPERATOR_INSTRUCTIONS,
        TrueForgeCommitOperator,
    )

    run = await commit_harness.drive_to_approval(incident())
    operator = McpCommitOperator(commit_harness.mcp)
    await build_coordinator(commit_harness, operator).approve(run.run_id, actor="human")

    # Nothing the operator sends carries capability material.
    assert "capability_token" not in str(operator.calls)
    assert set(operator.calls[0]) <= {"run_id", "world_id", "expected_action_id"}

    spec = TrueForgeCommitOperator(None, model="fake/model", bindings=None).agent_spec()
    rendered = str(spec) + COMMIT_OPERATOR_INSTRUCTIONS
    assert "capability_token" not in rendered
    assert "cap_" not in rendered

    # The commit tool is the only destructive tool this agent can even see.
    assert spec["mcp_servers"][0]["enable_tools"] == [COMMIT_TOOL_NAME]


def test_no_rest_route_bypasses_capability_enforcement() -> None:
    """22. Every mutating HTTP route is accounted for, and none commits directly.

    A new POST that changes reality would have to be added to this list
    deliberately, which is the point: the allow-list is the guard.
    """
    from app.main import app

    # The published contract, not the internal route objects: this is exactly
    # what a browser can reach.
    mutating = {
        f"{method.upper()} {path}"
        for path, operations in app.openapi()["paths"].items()
        for method in operations
        if method.upper() in {"POST", "PUT", "PATCH", "DELETE"}
    }

    assert mutating == {
        # Creates a run. Inert: no world, no action, no reality.
        "POST /api/v1/runs",
        # Runs the deterministic pipeline up to the gate. Never commits.
        "POST /api/v1/runs/{run_id}/execute-demo-worlds",
        # Issues a one-time capability, and only for an APPROVED run whose
        # binding still validates. Issuing is not spending.
        "POST /api/v1/runs/{run_id}/commit-capability",
        # The one human decision. Commits only what is already bound, through
        # the destructive MCP tool and its capability gate.
        "POST /api/v1/runs/{run_id}/approval",
        # Starts an agent run. Stops at the gate.
        "POST /api/v1/agent-runs",
        # Demo-only scenario reset, refused when BRANCHPOINT_ENV=production.
        "POST /api/v1/demo/reset",
    }


async def test_reality_is_unchanged_before_approval(commit_harness: CommitHarness) -> None:
    """23. Everything up to the gate is counterfactual — reality is byte-identical."""
    before = await commit_harness.engine.reality()

    run = await commit_harness.drive_to_approval(incident())

    after = await commit_harness.engine.reality()
    assert run.status is RunStatus.AWAITING_APPROVAL
    assert after.pricing_flag == before.pricing_flag
    assert after.pricing_deployment == before.pricing_deployment
    assert after.pricing_capacity == before.pricing_capacity
    assert after.orders_schema_version == before.orders_schema_version


# ----- helpers ---------------------------------------------------------------


async def _harness_with_failing_verifier() -> CommitHarness:
    """An otherwise identical stack whose independent verifier always fails."""
    engine = DemoProductionEngine()
    capability_store = CapabilityStore()
    repository = InMemoryRunRepository()
    events = InMemoryEventSink()

    class FailingVerifier(DemoRealityVerifier):
        async def verify(self, run, commit_receipt):
            checks = await super().verify(run, commit_receipt)
            return tuple(check.model_copy(update={"passed": False}) for check in checks)

    orchestrator = BranchpointOrchestrator(
        repository=repository,
        events=events,
        reality_reader=DemoRealityReader(engine),
        planner=HeroCandidatePlanner(),
        world_executor=DemoWorldExecutor(engine),
        adversarial_tester=HeroAdversarialTester(engine),
        mutator=DemoRealityMutator(engine, capability_store),
        verifier=FailingVerifier(engine),
    )
    mcp = build_mcp_server(
        engine=engine,
        capability_store=capability_store,
        run_repository=repository,
        orchestrator_factory=lambda: orchestrator,
    )
    return CommitHarness(
        engine=engine,
        orchestrator=orchestrator,
        mcp=MCPTestHarness(mcp, engine, capability_store, repository),
        events=events,
    )
