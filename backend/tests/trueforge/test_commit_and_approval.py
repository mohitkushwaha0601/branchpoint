"""The human-approval and destructive-commit path, end to end (no model calls).

Drives a full run with deterministic demo adapters so the *approval and commit
gates* are exercised for real, then calls the destructive MCP commit tool
exactly the way the TrueForge commit operator does once BRANCHPOINT resumes it.

The human decision is recorded in BRANCHPOINT *first* — the tool records no
approval of its own — so every commit here is preceded by an explicit
``decide_approval``, exactly as ``POST /api/v1/runs/{run_id}/approval`` does.
"""

import pytest

from app.application.orchestration.orchestrator import BranchpointOrchestrator
from app.domain.commits.models import CommitStatus
from app.domain.errors import InvariantViolationError
from app.domain.incidents.models import Incident, IncidentSeverity
from app.domain.primitives import new_id, utc_now
from app.domain.runs.lifecycle import RunStatus
from app.domain.verification.models import VerificationStatus
from app.infrastructure.demo.adapters import (
    DemoRealityMutator,
    DemoRealityReader,
    DemoRealityVerifier,
    DemoWorldExecutor,
)
from app.infrastructure.demo.capability import CapabilityStore
from app.infrastructure.demo.engine import DemoProductionEngine
from app.infrastructure.demo.hero import HeroAdversarialTester, HeroCandidatePlanner
from app.infrastructure.persistence.memory import InMemoryEventSink, InMemoryRunRepository
from app.mcp.server import COMMIT_TOOL_NAME
from tests.mcp.conftest import mcp_session
from tests.trueforge.conftest import CommitHarness


async def approve(harness: CommitHarness, run) -> None:
    """Record the human decision, exactly as the approval endpoint does."""
    await harness.orchestrator.decide_approval(run.run_id, approved=True, actor="human")


def incident() -> Incident:
    return Incident(
        incident_id=new_id("incident"),
        title="Checkout error rate at 41.3%",
        goal="Return checkout error rate below 2%",
        severity=IncidentSeverity.CRITICAL,
        detected_at=utc_now(),
    )


async def test_commit_tool_requires_a_granted_approval(commit_harness: CommitHarness) -> None:
    """An agent cannot commit a run no human has approved."""
    run = await commit_harness.orchestrator.create_run(incident())

    async with mcp_session(commit_harness.mcp) as session:
        result = await session.call_tool(
            COMMIT_TOOL_NAME, {"run_id": run.run_id, "world_id": "world_1"}
        )

    assert result.is_error is True
    assert "no granted human approval" in result.content[0].text


async def test_commit_tool_refuses_a_run_still_awaiting_approval(
    commit_harness: CommitHarness,
) -> None:
    """Reaching the gate is not the same as passing it: reality stays untouched."""
    run = await commit_harness.drive_to_approval(incident())
    recommended = run.comparison.recommended_world_id

    async with mcp_session(commit_harness.mcp) as session:
        result = await session.call_tool(
            COMMIT_TOOL_NAME, {"run_id": run.run_id, "world_id": recommended}
        )

    assert result.is_error is True
    assert "no granted human approval" in result.content[0].text
    assert (await commit_harness.engine.reality()).pricing_flag.enabled is True


async def test_commit_tool_refuses_a_world_that_is_not_recommended(
    commit_harness: CommitHarness,
) -> None:
    """The agent cannot redirect the commit to a vetoed or non-recommended world."""
    run = await commit_harness.drive_to_approval(incident())
    recommended = run.comparison.recommended_world_id
    other = next(w.world_id for w in run.worlds if w.world_id != recommended)
    await approve(commit_harness, run)

    async with mcp_session(commit_harness.mcp) as session:
        result = await session.call_tool(
            COMMIT_TOOL_NAME, {"run_id": run.run_id, "world_id": other}
        )

    assert result.is_error is True
    assert "the human approved world" in result.content[0].text
    assert (await commit_harness.engine.reality()).pricing_flag.enabled is True


async def test_commit_tool_refuses_a_mismatched_action_id(commit_harness: CommitHarness) -> None:
    """A changed action after approval is refused via the expected-action check."""
    run = await commit_harness.drive_to_approval(incident())
    recommended = run.comparison.recommended_world_id
    await approve(commit_harness, run)

    async with mcp_session(commit_harness.mcp) as session:
        result = await session.call_tool(
            COMMIT_TOOL_NAME,
            {
                "run_id": run.run_id,
                "world_id": recommended,
                "expected_action_id": "action_something_else",
            },
        )

    assert result.is_error is True
    assert "not the expected" in result.content[0].text


async def test_approved_commit_mutates_reality_and_verifies(
    commit_harness: CommitHarness,
) -> None:
    """The full sanctioned path: approve -> capability -> mutate -> verify."""
    run = await commit_harness.drive_to_approval(incident())
    recommended = run.comparison.recommended_world_id
    assert (await commit_harness.engine.reality()).pricing_flag.enabled is True
    await approve(commit_harness, run)

    async with mcp_session(commit_harness.mcp) as session:
        result = await session.call_tool(
            COMMIT_TOOL_NAME, {"run_id": run.run_id, "world_id": recommended}
        )

    assert result.is_error is not True
    body = result.structured_content
    assert body["commit_status"] == str(CommitStatus.SUCCEEDED)
    assert body["verification_status"] == str(VerificationStatus.PASSED)
    assert body["run_status"] == str(RunStatus.SUCCEEDED)

    reality = await commit_harness.engine.reality()
    assert reality.pricing_flag.enabled is False


async def test_commit_never_returns_a_capability_token(commit_harness: CommitHarness) -> None:
    """The model must never see capability material."""
    run = await commit_harness.drive_to_approval(incident())
    recommended = run.comparison.recommended_world_id
    await approve(commit_harness, run)

    async with mcp_session(commit_harness.mcp) as session:
        result = await session.call_tool(
            COMMIT_TOOL_NAME, {"run_id": run.run_id, "world_id": recommended}
        )

    payload = str(result.structured_content) + str(result.content[0].text)
    assert "token" not in payload.lower()
    for field in ("capability_token", "cap_"):
        assert field not in payload


async def test_commit_is_not_repeatable(commit_harness: CommitHarness) -> None:
    """A second commit attempt cannot re-mutate reality (capability is one-time)."""
    run = await commit_harness.drive_to_approval(incident())
    recommended = run.comparison.recommended_world_id
    await approve(commit_harness, run)

    async with mcp_session(commit_harness.mcp) as session:
        first = await session.call_tool(
            COMMIT_TOOL_NAME, {"run_id": run.run_id, "world_id": recommended}
        )
        second = await session.call_tool(
            COMMIT_TOOL_NAME, {"run_id": run.run_id, "world_id": recommended}
        )

    assert first.is_error is not True
    assert second.is_error is True


async def test_orchestrator_still_refuses_commit_without_approval(
    commit_harness: CommitHarness,
) -> None:
    """Phase 1's own gate is unchanged and still authoritative."""
    run = await commit_harness.drive_to_approval(incident())

    with pytest.raises(InvariantViolationError, match="commit requires approval"):
        await commit_harness.orchestrator.commit(run.run_id)


async def test_verification_failure_prevents_succeeded(monkeypatch) -> None:
    """A commit that applies but fails verification never reports success."""
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

    run = await orchestrator.drive_to_approval(incident())
    run = await orchestrator.decide_approval(run.run_id, approved=True, actor="human")
    run = await orchestrator.commit(run.run_id)
    assert run.commit_receipt.status is CommitStatus.SUCCEEDED

    run = await orchestrator.verify(run.run_id)

    assert run.verification.status is VerificationStatus.FAILED
    assert run.status is RunStatus.FAILED
    assert run.status is not RunStatus.SUCCEEDED
