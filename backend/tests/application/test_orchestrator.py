"""Orchestration of a full run against in-memory test doubles."""

import pytest

from app.application.errors import PortNotConfiguredError, RunNotFoundError
from app.application.orchestration.orchestrator import BranchpointOrchestrator
from app.domain.approvals.models import ApprovalStatus
from app.domain.commits.models import CommitStatus
from app.domain.errors import InvariantViolationError
from app.domain.events import RunEventType
from app.domain.evidence.models import EvidenceKind
from app.domain.runs.lifecycle import RunStatus
from app.domain.verification.models import VerificationCheck, VerificationStatus
from app.domain.worlds.models import (
    AdversarialReport,
    CounterexampleStatus,
    WorldExecutionReport,
    WorldVerdict,
)
from app.infrastructure.persistence.memory import InMemoryEventSink, InMemoryRunRepository
from tests.doubles import (
    ExplodingWorldExecutor,
    RecordingMutator,
    ScriptedAdversarialTester,
    ScriptedWorldExecutor,
    SequentialIds,
    StubPlanner,
    StubRealityReader,
    StubVerifier,
)
from tests.factories import (
    FIXED_TIME,
    make_action,
    make_counterexample,
    make_evidence,
    make_incident,
    make_observed_state,
    make_outcome,
)

PASSING_CHECK = VerificationCheck(
    key="checkout_error_rate",
    description="checkout error rate is below 1%",
    passed=True,
    observed=0.003,
    expected=0.01,
)
FAILING_CHECK = VerificationCheck(
    key="checkout_error_rate",
    description="checkout error rate is below 1%",
    passed=False,
    observed=0.38,
    expected=0.01,
)


def build_orchestrator(
    *,
    candidates=None,
    executor=None,
    tester=None,
    mutator=None,
    verifier=None,
    repository=None,
    events=None,
) -> tuple[BranchpointOrchestrator, InMemoryRunRepository, InMemoryEventSink]:
    """Wire an orchestrator with in-memory doubles."""
    repository = repository or InMemoryRunRepository()
    events = events or InMemoryEventSink()
    actions = candidates if candidates is not None else (make_action("action_1"),)
    orchestrator = BranchpointOrchestrator(
        repository=repository,
        events=events,
        reality_reader=StubRealityReader(make_observed_state()),
        planner=StubPlanner(actions),
        world_executor=executor
        or ScriptedWorldExecutor(
            {
                action.action_id: WorldExecutionReport(
                    outcome=make_outcome(),
                    evidence=(make_evidence(f"{action.action_id}_metric"),),
                )
                for action in actions
            }
        ),
        adversarial_tester=tester or ScriptedAdversarialTester({}),
        mutator=mutator or RecordingMutator(),
        verifier=verifier or StubVerifier((PASSING_CHECK,)),
        clock=lambda: FIXED_TIME,
        id_factory=SequentialIds(),
    )
    return orchestrator, repository, events


async def test_happy_path_reaches_succeeded() -> None:
    mutator = RecordingMutator()
    orchestrator, repository, events = build_orchestrator(mutator=mutator)

    run = await orchestrator.drive_to_approval(make_incident())
    assert run.status is RunStatus.AWAITING_APPROVAL
    assert run.comparison is not None
    assert run.comparison.recommended_world_id == run.selected_world_id
    assert run.worlds[0].verdict is WorldVerdict.SURVIVED

    run = await orchestrator.decide_approval(
        run.run_id, approved=True, actor="sre@example.com", reason="lowest blast radius"
    )
    assert run.status is RunStatus.APPROVED
    assert run.approval is not None
    assert run.approval.status is ApprovalStatus.APPROVED

    run = await orchestrator.commit(run.run_id)
    assert run.commit_receipt is not None
    assert run.commit_receipt.status is CommitStatus.SUCCEEDED
    assert mutator.applied == [(run.selected_world_id, "action_1")]

    run = await orchestrator.verify(run.run_id)
    assert run.status is RunStatus.SUCCEEDED
    assert run.verification is not None
    assert run.verification.status is VerificationStatus.PASSED

    stored = await repository.get(run.run_id)
    assert stored is not None
    assert stored.status is RunStatus.SUCCEEDED

    timeline = [event.event_type for event in await events.events_for(run.run_id)]
    assert timeline == [
        RunEventType.RUN_CREATED,
        RunEventType.OBSERVATION_COMPLETED,
        RunEventType.CANDIDATES_PLANNED,
        RunEventType.WORLD_CREATED,
        RunEventType.WORLD_EXECUTION_STARTED,
        RunEventType.WORLD_EXECUTION_COMPLETED,
        RunEventType.DOPPELGANGER_STARTED,
        RunEventType.WORLD_SURVIVED,
        RunEventType.COMPARISON_COMPLETED,
        RunEventType.APPROVAL_REQUESTED,
        RunEventType.APPROVAL_GRANTED,
        RunEventType.COMMIT_STARTED,
        RunEventType.COMMIT_COMPLETED,
        RunEventType.VERIFICATION_COMPLETED,
    ]


async def test_commit_is_impossible_without_approval() -> None:
    orchestrator, _, _ = build_orchestrator()
    run = await orchestrator.drive_to_approval(make_incident())

    with pytest.raises(InvariantViolationError, match="commit requires approval"):
        await orchestrator.commit(run.run_id)


async def test_commit_is_impossible_after_a_rejected_approval() -> None:
    orchestrator, _, _ = build_orchestrator()
    run = await orchestrator.drive_to_approval(make_incident())

    run = await orchestrator.decide_approval(
        run.run_id, approved=False, actor="sre@example.com", reason="not now"
    )

    assert run.status is RunStatus.REJECTED
    with pytest.raises(InvariantViolationError, match="commit requires approval"):
        await orchestrator.commit(run.run_id)


async def test_verification_requires_a_successful_commit() -> None:
    orchestrator, _, _ = build_orchestrator()
    run = await orchestrator.drive_to_approval(make_incident())
    run = await orchestrator.decide_approval(run.run_id, approved=True, actor="sre@example.com")

    with pytest.raises(InvariantViolationError, match="verification follows a successful commit"):
        await orchestrator.verify(run.run_id)


async def test_failed_verification_does_not_mean_success() -> None:
    orchestrator, _, _ = build_orchestrator(verifier=StubVerifier((FAILING_CHECK,)))
    run = await orchestrator.drive_to_approval(make_incident())
    run = await orchestrator.decide_approval(run.run_id, approved=True, actor="sre@example.com")
    run = await orchestrator.commit(run.run_id)

    run = await orchestrator.verify(run.run_id)

    assert run.commit_receipt is not None
    assert run.commit_receipt.status is CommitStatus.SUCCEEDED
    assert run.status is RunStatus.FAILED
    assert run.verification is not None
    assert run.verification.status is VerificationStatus.FAILED


async def test_run_is_rejected_when_no_candidates_are_proposed() -> None:
    orchestrator, _, events = build_orchestrator(candidates=())

    run = await orchestrator.create_run(make_incident())
    run = await orchestrator.observe(run.run_id)
    run = await orchestrator.plan(run.run_id)

    assert run.status is RunStatus.REJECTED
    assert RunEventType.RUN_REJECTED in [
        event.event_type for event in await events.events_for(run.run_id)
    ]


async def test_run_is_rejected_when_nothing_survives() -> None:
    action = make_action("action_1")
    tester = ScriptedAdversarialTester(
        {
            "action_1": AdversarialReport(
                counterexamples=(
                    make_counterexample(
                        "cx_1",
                        "world_1",
                        status=CounterexampleStatus.REPRODUCED,
                        evidence_ids=("attack_1",),
                    ),
                ),
                evidence=(
                    make_evidence(
                        "attack_1",
                        kind=EvidenceKind.TEST_RESULT,
                        passed=False,
                        machine_verifiable=True,
                    ),
                ),
            )
        }
    )
    orchestrator, _, _ = build_orchestrator(candidates=(action,), tester=tester)

    run = await orchestrator.drive_to_approval(make_incident())

    assert run.status is RunStatus.REJECTED
    assert run.approval is None
    assert run.comparison is not None
    assert run.comparison.recommended_world_id is None


async def test_deterministic_tie_blocks_automatic_approval() -> None:
    actions = (make_action("action_1"), make_action("action_2"))
    orchestrator, _, _ = build_orchestrator(candidates=actions)

    run = await orchestrator.drive_to_approval(make_incident())

    assert run.comparison is not None
    assert run.comparison.is_tied
    assert run.status is RunStatus.REJECTED
    assert run.approval is None


async def test_one_broken_world_does_not_abort_the_run() -> None:
    actions = (make_action("action_1"), make_action("action_2"))
    executor = ExplodingWorldExecutor(
        "action_1",
        {
            "action_2": WorldExecutionReport(
                outcome=make_outcome(), evidence=(make_evidence("action_2_metric"),)
            )
        },
    )
    orchestrator, _, _ = build_orchestrator(candidates=actions, executor=executor)

    run = await orchestrator.drive_to_approval(make_incident())

    verdicts = {world.candidate_action.action_id: world.verdict for world in run.worlds}
    assert verdicts["action_1"] is WorldVerdict.EXECUTION_FAILED
    assert verdicts["action_2"] is WorldVerdict.SURVIVED
    assert run.status is RunStatus.AWAITING_APPROVAL


async def test_unconfigured_port_fails_loudly() -> None:
    orchestrator = BranchpointOrchestrator(
        repository=InMemoryRunRepository(),
        events=InMemoryEventSink(),
        clock=lambda: FIXED_TIME,
        id_factory=SequentialIds(),
    )
    run = await orchestrator.create_run(make_incident())

    with pytest.raises(PortNotConfiguredError, match="RealityReader"):
        await orchestrator.observe(run.run_id)


async def test_unknown_run_is_reported() -> None:
    orchestrator, _, _ = build_orchestrator()

    with pytest.raises(RunNotFoundError):
        await orchestrator.observe("run_does_not_exist")


async def test_approval_cannot_be_decided_before_it_is_requested() -> None:
    orchestrator, _, _ = build_orchestrator()
    run = await orchestrator.create_run(make_incident())

    with pytest.raises(InvariantViolationError, match="decision requires a pending approval"):
        await orchestrator.decide_approval(run.run_id, approved=True, actor="sre@example.com")
